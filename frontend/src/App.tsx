import cytoscape from "cytoscape";
import {
  AlertTriangle,
  ArrowRight,
  Bolt,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Database,
  FileSearch,
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  Network,
  PanelRightOpen,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import type {
  AliasData,
  DesignDocument,
  DesignDocuments,
  GraphData,
  Impact,
  Job,
  Overview,
  Project,
  Report,
  ViewName,
} from "./types";

const VIEWS: Array<{ id: ViewName; label: string; icon: typeof LayoutDashboard }> = [
  { id: "dashboard", label: "概要", icon: LayoutDashboard },
  { id: "impact-board", label: "変更レビュー", icon: Bolt },
  { id: "graph", label: "ナレッジグラフ", icon: Network },
  { id: "aliases", label: "Alias", icon: GitCompareArrows },
  { id: "jobs", label: "ジョブと監査", icon: ListChecks },
  { id: "settings", label: "設定", icon: Settings },
];

const TERMINAL_STATES = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

function currentView(): ViewName {
  const value = window.location.pathname.split("/").filter(Boolean).at(-1);
  return VIEWS.some((view) => view.id === value) ? (value as ViewName) : "dashboard";
}

function projectIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("project_id");
}

function updateUrl(view: ViewName, projectId: string | null, replace = false): void {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const url = `/ui/${view}${params.size ? `?${params.toString()}` : ""}`;
  window.history[replace ? "replaceState" : "pushState"]({}, "", url);
}

export function App() {
  const [view, setView] = useState<ViewName>(currentView);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(projectIdFromUrl);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [aliases, setAliases] = useState<AliasData | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [design, setDesign] = useState<DesignDocuments | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadProject = useCallback(async (nextProjectId: string) => {
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      api.overview(nextProjectId),
      api.report(nextProjectId),
      api.graph(nextProjectId),
      api.aliases(nextProjectId),
      api.jobs(nextProjectId),
      api.designDocuments(nextProjectId),
    ]);
    const [overviewResult, reportResult, graphResult, aliasResult, jobsResult, designResult] = results;
    if (overviewResult.status === "rejected") {
      setError(overviewResult.reason instanceof Error ? overviewResult.reason.message : "案件を読み込めませんでした");
      setLoading(false);
      return;
    }
    setOverview(overviewResult.value);
    setReport(reportResult.status === "fulfilled" ? reportResult.value : null);
    setGraph(graphResult.status === "fulfilled" ? graphResult.value : null);
    setAliases(aliasResult.status === "fulfilled" ? aliasResult.value : null);
    setJobs(jobsResult.status === "fulfilled" ? jobsResult.value.jobs : []);
    setDesign(designResult.status === "fulfilled" ? designResult.value : null);
    setLoading(false);
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.projects();
      setProjects(response.projects);
      const requested = projectIdFromUrl();
      const selected = response.projects.find((project) => project.project_id === requested) ?? response.projects[0];
      if (!selected) {
        setProjectId(null);
        setLoading(false);
        return;
      }
      setProjectId(selected.project_id);
      updateUrl(currentView(), selected.project_id, true);
      await loadProject(selected.project_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "GUIを初期化できませんでした");
      setLoading(false);
    }
  }, [loadProject]);

  useEffect(() => {
    void bootstrap();
    const onPopState = () => {
      setView(currentView());
      const nextProjectId = projectIdFromUrl();
      if (nextProjectId && nextProjectId !== projectId) {
        setProjectId(nextProjectId);
        void loadProject(nextProjectId);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [bootstrap, loadProject, projectId]);

  const navigate = (nextView: ViewName) => {
    setView(nextView);
    updateUrl(nextView, projectId);
  };

  const selectProject = (nextProjectId: string) => {
    setProjectId(nextProjectId);
    updateUrl(view, nextProjectId, true);
    void loadProject(nextProjectId);
  };

  const refresh = () => projectId && loadProject(projectId);

  return (
    <div className="app-shell">
      <Sidebar view={view} onNavigate={navigate} overview={overview} />
      <div className="app-main">
        <Topbar
          projects={projects}
          projectId={projectId}
          overview={overview}
          loading={loading}
          onProjectChange={selectProject}
          onRefresh={refresh}
        />
        <main className={`app-content view-${view}`}>
          {error && <ErrorBanner message={error} onRetry={() => void bootstrap()} />}
          {!error && loading && <LoadingState label="案件データを読み込んでいます" />}
          {!error && !loading && !projectId && <NoProject />}
          {!error && !loading && projectId && (
            <ActiveView
              view={view}
              projectId={projectId}
              overview={overview}
              report={report}
              graph={graph}
              aliases={aliases}
              jobs={jobs}
              design={design}
              onDesignChange={setDesign}
              onRefresh={refresh}
              onNavigate={navigate}
            />
          )}
        </main>
      </div>
      <div id="page-status" className="sr-only" role="status" aria-live="polite">
        {loading ? "読み込み中" : error || "準備完了"}
      </div>
    </div>
  );
}

function Sidebar({ view, onNavigate, overview }: { view: ViewName; onNavigate: (view: ViewName) => void; overview: Overview | null }) {
  return (
    <aside className="sidebar" aria-label="メインナビゲーション">
      <div className="brand-row">
        <span className="brand-mark" aria-hidden="true">SI</span>
        <span><strong>SpecImpact</strong><small>Evidence workspace</small></span>
      </div>
      <nav className="primary-nav">
        <p className="nav-label">Workspace</p>
        {VIEWS.slice(0, 4).map(({ id, label, icon: Icon }) => (
          <button key={id} className={view === id ? "active" : ""} onClick={() => onNavigate(id)} aria-current={view === id ? "page" : undefined}>
            <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
          </button>
        ))}
        <p className="nav-label">System</p>
        {VIEWS.slice(4).map(({ id, label, icon: Icon }) => (
          <button key={id} className={view === id ? "active" : ""} onClick={() => onNavigate(id)} aria-current={view === id ? "page" : undefined}>
            <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-status">
        <div><ShieldCheck size={16} /><strong>Local console</strong></div>
        <dl>
          <dt>Bind</dt><dd>127.0.0.1</dd>
          <dt>Backend</dt><dd>local JSONL</dd>
          <dt>External</dt><dd>{overview?.llm.external_transmission ? "approval" : "none"}</dd>
        </dl>
      </div>
    </aside>
  );
}

function Topbar({ projects, projectId, overview, loading, onProjectChange, onRefresh }: {
  projects: Project[];
  projectId: string | null;
  overview: Overview | null;
  loading: boolean;
  onProjectChange: (projectId: string) => void;
  onRefresh: () => void;
}) {
  const provider = overview?.llm.enabled
    ? `${overview.llm.provider ?? "LLM"} / ${overview.llm.model ?? "default"}`
    : "Local fallback";
  return (
    <header className="topbar">
      <label className="project-select">
        <CircleDot size={15} aria-hidden="true" />
        <span className="sr-only">案件</span>
        <select value={projectId ?? ""} onChange={(event) => onProjectChange(event.target.value)} disabled={!projects.length}>
          {!projects.length && <option value="">案件なし</option>}
          {projects.map((project) => <option value={project.project_id} key={project.project_id}>{project.display_name}</option>)}
        </select>
      </label>
      <span className={`provider-pill ${overview?.llm.enabled ? "enabled" : "local"}`}><Bolt size={14} />{provider}</span>
      <span className="privacy-pill"><ShieldCheck size={14} />Local only</span>
      <span className="topbar-spacer" />
      <button className="icon-button" type="button" onClick={onRefresh} disabled={loading} title="再読み込み" aria-label="案件データを再読み込み">
        <RefreshCw size={17} className={loading ? "spin" : ""} />
      </button>
    </header>
  );
}

function ActiveView(props: {
  view: ViewName;
  projectId: string;
  overview: Overview | null;
  report: Report | null;
  graph: GraphData | null;
  aliases: AliasData | null;
  jobs: Job[];
  design: DesignDocuments | null;
  onDesignChange: (design: DesignDocuments) => void;
  onRefresh: () => void;
  onNavigate: (view: ViewName) => void;
}) {
  if (props.view === "dashboard") return <Dashboard overview={props.overview} report={props.report} jobs={props.jobs} onNavigate={props.onNavigate} />;
  if (props.view === "impact-board") return <ImpactWorkspace {...props} />;
  if (props.view === "graph") return <GraphView graph={props.graph} />;
  if (props.view === "aliases") return <AliasesView aliases={props.aliases} />;
  if (props.view === "jobs") return <JobsView jobs={props.jobs} />;
  return <SettingsView overview={props.overview} />;
}

function ViewHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode }) {
  return (
    <header className="view-header">
      <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>
      {actions && <div className="view-actions">{actions}</div>}
    </header>
  );
}

function Dashboard({ overview, report, jobs, onNavigate }: { overview: Overview | null; report: Report | null; jobs: Job[]; onNavigate: (view: ViewName) => void }) {
  const counts = overview?.counts ?? {};
  const impacts = groupedImpacts(report);
  const pending = impacts.filter((item) => item.priority !== "hidden").length;
  return (
    <div className="page page-dashboard">
      <ViewHeader eyebrow="Workspace overview" title={overview?.project.display_name ?? "案件概要"} description="設計書からレビュー判断まで、現在の状態と次の作業を確認します。" />
      <section className="metrics" aria-label="グラフ件数">
        {["documents", "artifacts", "entities", "relations", "evidence"].map((key) => (
          <div className="metric" key={key}><span>{key}</span><strong>{counts[key] ?? 0}</strong></div>
        ))}
      </section>
      <div className="dashboard-grid">
        <section className="section-panel next-action">
          <div className="section-heading"><span><Bolt size={17} />次に確認すること</span></div>
          {report ? (
            <button className="next-action-row" onClick={() => onNavigate("impact-board")}>
              <span className="priority-mark must" /><span><strong>{report.change.title}</strong><small>{pending}件のレビュー候補</small></span><ChevronRight size={17} />
            </button>
          ) : (
            <div className="empty-inline"><FileSearch size={20} /><span>分析runがありません。CLIまたは変更レビューから分析を開始してください。</span></div>
          )}
          <button className="next-action-row" onClick={() => onNavigate("aliases")}>
            <span className="priority-mark alias" /><span><strong>Alias候補</strong><small>表記揺れと根拠を確認</small></span><ChevronRight size={17} />
          </button>
        </section>
        <section className="section-panel system-health">
          <div className="section-heading"><span><ShieldCheck size={17} />Project health</span></div>
          <HealthRow ok={Boolean(overview?.initialized)} label="Local store" value={overview?.initialized ? "ready" : "not initialized"} />
          <HealthRow ok={Boolean(overview?.latest_run)} label="Latest run" value={overview?.latest_run ?? "none"} />
          <HealthRow ok={!overview?.llm.external_transmission} label="External transmission" value={overview?.llm.external_transmission ? "approval required" : "not required"} />
          <HealthRow ok={!jobs.some((job) => job.state === "failed")} label="Recent jobs" value={`${jobs.length} recorded`} />
        </section>
      </div>
    </div>
  );
}

function HealthRow({ ok, label, value }: { ok: boolean; label: string; value: string }) {
  return <div className="health-row">{ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}<span>{label}</span><strong>{value}</strong></div>;
}

type RankedImpact = Impact & { priority: string };

function groupedImpacts(report: Report | null): RankedImpact[] {
  if (!report) return [];
  return (["must_review", "should_review", "may_review", "hidden"] as const).flatMap((priority) =>
    report[priority].map((impact) => ({ ...impact, priority })),
  );
}

function ImpactWorkspace({ projectId, report, design, onDesignChange, onRefresh }: {
  projectId: string;
  report: Report | null;
  design: DesignDocuments | null;
  onDesignChange: (design: DesignDocuments) => void;
  onRefresh: () => void;
}) {
  const impacts = useMemo(() => groupedImpacts(report).filter((impact) => impact.priority !== "hidden"), [report]);
  const [selectedImpactId, setSelectedImpactId] = useState(impacts[0]?.artifact_id ?? "");
  const [selectedDocument, setSelectedDocument] = useState("");
  const [query, setQuery] = useState("");
  const [changeText, setChangeText] = useState("");
  const [analysisState, setAnalysisState] = useState<"idle" | "running">("idle");
  const [message, setMessage] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(true);

  useEffect(() => {
    if (!selectedImpactId && impacts[0]) setSelectedImpactId(impacts[0].artifact_id);
  }, [impacts, selectedImpactId]);

  useEffect(() => {
    if (!selectedDocument && design?.documents[0]) setSelectedDocument(design.documents[0].file);
  }, [design, selectedDocument]);

  const selectedImpact = impacts.find((impact) => impact.artifact_id === selectedImpactId) ?? impacts[0];
  const selectedDoc = design?.documents.find((document) => document.file === selectedDocument) ?? design?.documents[0];

  const selectImpact = async (impact: RankedImpact) => {
    setSelectedImpactId(impact.artifact_id);
    try {
      const nextDesign = await api.designDocuments(projectId, impact.evidence_ids);
      onDesignChange(nextDesign);
      const highlighted = nextDesign.documents.find((document) => document.highlight_count > 0);
      setSelectedDocument(highlighted?.file ?? nextDesign.documents[0]?.file ?? "");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "設計書を読み込めませんでした");
    }
  };

  const runAnalysis = async () => {
    if (!changeText.trim()) {
      setMessage("変更内容を入力してください。");
      return;
    }
    setAnalysisState("running");
    setMessage("外部送信の有無を確認しています。");
    const params = { body: changeText.trim(), design_document: selectedDocument };
    try {
      const preview = await api.externalPreview(projectId, "analyze_text_llm_first", params);
      const approved = !preview.required || window.confirm(formatTransmissionPreview(preview.transmissions));
      if (!approved) {
        setMessage("分析をキャンセルしました。");
        setAnalysisState("idle");
        return;
      }
      const created = await api.enqueue(projectId, "analyze_text_llm_first", params, preview.required);
      setMessage("分析中です。設計書とグラフから候補を検証しています。");
      await waitForJob(projectId, created.job.job_id);
      setMessage("分析が完了しました。");
      onRefresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "分析に失敗しました。");
    } finally {
      setAnalysisState("idle");
    }
  };

  const filtered = impacts.filter((impact) => `${impact.display_name} ${impact.artifact_id} ${impact.reason}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className={`review-page ${inspectorOpen ? "inspector-open" : ""}`}>
      <section className="review-main">
        <ViewHeader
          eyebrow="Change review"
          title={report?.change.title ?? "変更影響レビュー"}
          description="候補、設計書、根拠を同じ文脈で確認します。LLM出力はレビュー候補です。"
          actions={!inspectorOpen ? <button className="icon-button" onClick={() => setInspectorOpen(true)} title="Inspectorを開く" aria-label="Inspectorを開く"><PanelRightOpen size={18} /></button> : undefined}
        />
        <section className="change-composer" aria-label="変更影響分析">
          <label><span>起点となる設計書</span><select value={selectedDocument} onChange={(event) => setSelectedDocument(event.target.value)}><option value="">案件全体</option>{design?.documents.map((document) => <option value={document.file} key={document.file}>{document.title}</option>)}</select></label>
          <label className="change-input"><span>変更内容</span><textarea value={changeText} onChange={(event) => setChangeText(event.target.value)} placeholder="例: 利用限度額の上限を999万円から9999万円に変更する" rows={2} /></label>
          <button className="primary-button" onClick={() => void runAnalysis()} disabled={analysisState === "running"}>{analysisState === "running" ? <LoaderCircle className="spin" size={17} /> : <Bolt size={17} />}影響分析</button>
        </section>
        {message && <p className="inline-status" role="status">{message}</p>}
        <div className="review-workspace">
          <section className="candidate-pane" aria-label="影響候補">
            <div className="pane-toolbar"><label className="search-control"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="候補を検索" /></label><span>{filtered.length}</span></div>
            <div className="candidate-list">
              {filtered.length ? filtered.map((impact) => <ImpactRow key={impact.artifact_id} impact={impact} selected={selectedImpact?.artifact_id === impact.artifact_id} onSelect={() => void selectImpact(impact)} />) : <EmptyState icon={FileSearch} title="候補がありません" body="変更内容を分析するか、検索条件を変更してください。" compact />}
            </div>
          </section>
          <section className="source-pane" aria-label="設計書参照">
            <div className="pane-toolbar source-toolbar"><div><FileText size={16} /><strong>{selectedDoc?.title ?? "設計書"}</strong></div>{selectedDoc && <select value={selectedDoc.file} onChange={(event) => setSelectedDocument(event.target.value)}>{design?.documents.map((document) => <option value={document.file} key={document.file}>{document.title} ({document.highlight_count})</option>)}</select>}</div>
            <DocumentViewer document={selectedDoc} />
          </section>
        </div>
      </section>
      {inspectorOpen && <ImpactInspector impact={selectedImpact} onClose={() => setInspectorOpen(false)} />}
    </div>
  );
}

function ImpactRow({ impact, selected, onSelect }: { impact: RankedImpact; selected: boolean; onSelect: () => void }) {
  return (
    <button className={`candidate-row ${selected ? "selected" : ""}`} onClick={onSelect}>
      <span className={`priority-dot ${impact.priority}`} />
      <span className="candidate-copy"><strong>{impact.display_name}</strong><small>{impact.artifact_type} · {impact.evidence_ids.length} evidence</small><span>{impact.reason}</span></span>
      <ChevronRight size={16} />
    </button>
  );
}

function DocumentViewer({ document }: { document: DesignDocument | undefined }) {
  if (!document) return <EmptyState icon={FileText} title="設計書がありません" body="この案件には表示可能な設計書がありません。" />;
  if (document.cells.length) {
    return <div className="document-scroll"><table className="cell-table"><thead><tr><th>Sheet</th><th>Cell</th><th>Value</th></tr></thead><tbody>{document.cells.map((cell) => <tr key={`${cell.sheet_name}-${cell.cell}`} className={cell.highlight ? "highlight" : ""}><td>{cell.sheet_name}</td><td><code>{cell.cell}</code>{cell.merged_range && <small>{cell.merged_range}</small>}</td><td>{cell.value}</td></tr>)}</tbody></table></div>;
  }
  if (document.rows.length) {
    return <div className="document-scroll source-code">{document.rows.map((row) => <div className={`source-row ${row.highlight ? "highlight" : ""}`} key={row.line}><span>{row.line}</span><code>{row.text || " "}</code></div>)}</div>;
  }
  return <div className="document-scroll evidence-fallback">{document.evidence.map((evidence) => <article key={evidence.evidence_id}><code>{evidence.evidence_id}</code><p>{evidence.quote}</p></article>)}</div>;
}

function ImpactInspector({ impact, onClose }: { impact: RankedImpact | undefined; onClose: () => void }) {
  if (!impact) return <aside className="inspector"><button className="inspector-close icon-button" onClick={onClose} title="Inspectorを閉じる" aria-label="Inspectorを閉じる"><X size={17} /></button><EmptyState icon={FileSearch} title="候補を選択" body="候補を選ぶと根拠と経路を表示します。" compact /></aside>;
  return (
    <aside className="inspector" aria-label="Evidence Inspector">
      <div className="inspector-title"><button className="inspector-close icon-button" onClick={onClose} title="Inspectorを閉じる" aria-label="Inspectorを閉じる"><X size={17} /></button><p className="eyebrow">Evidence inspector</p><h2>{impact.display_name}</h2><div className="tag-row"><StatusTag value={impact.priority} /><StatusTag value={impact.evidence_strength} /><StatusTag value={impact.artifact_type} /></div></div>
      <InspectorSection title="Reason"><p>{impact.reason}</p></InspectorSection>
      <InspectorSection title="Relation path">{impact.relation_paths.map((path) => <code className="path-code" key={path}>{path}</code>)}</InspectorSection>
      <InspectorSection title="Required actions"><ul>{(impact.required_actions ?? []).map((action) => <li key={action}>{action}</li>)}</ul></InspectorSection>
      <InspectorSection title="Evidence">{impact.evidence?.map((evidence) => <article className="evidence-block" key={evidence.evidence_id}><code>{evidence.evidence_id}</code><small>{evidence.source_location.file} · L{evidence.source_location.line_start}</small><p>{evidence.quote}</p></article>)}</InspectorSection>
      {impact.llm_reason && <InspectorSection title="LLM hypothesis"><p>{impact.llm_reason}</p></InspectorSection>}
    </aside>
  );
}

function InspectorSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="inspector-section"><h3>{title}</h3>{children}</section>;
}

function StatusTag({ value }: { value: string }) {
  return <span className={`status-tag status-${value}`}>{value}</span>;
}

function GraphView({ graph }: { graph: GraphData | null }) {
  const container = useRef<HTMLDivElement>(null);
  const graphInstance = useRef<cytoscape.Core | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [search, setSearch] = useState("");
  useEffect(() => {
    if (!container.current || !graph?.nodes.length) return;
    const instance = cytoscape({
      container: container.current,
      elements: [...graph.nodes, ...graph.edges],
      layout: { name: "cose", animate: false, fit: true, padding: 48 },
      style: [
        { selector: "node", style: { "background-color": "#64748b", label: "data(label)", color: "#334155", "font-size": 11, "text-valign": "bottom", "text-margin-y": 8, width: 28, height: 28 } },
        { selector: 'node[kind = "artifact"]', style: { "background-color": "#4f46e5", width: 34, height: 34 } },
        { selector: 'node[kind = "entity"]', style: { "background-color": "#0891b2" } },
        { selector: "edge", style: { width: 1.5, "line-color": "#cbd5e1", "target-arrow-color": "#cbd5e1", "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(label)", "font-size": 8, color: "#64748b" } },
        { selector: 'edge[status = "confirmed"]', style: { "line-color": "#16a34a", "target-arrow-color": "#16a34a" } },
        { selector: 'edge[status = "unconfirmed"]', style: { "line-color": "#d97706", "target-arrow-color": "#d97706", "line-style": "dashed" } },
        { selector: ".dim", style: { opacity: 0.12 } },
        { selector: ":selected", style: { "border-color": "#f59e0b", "border-width": 4 } },
      ],
    });
    graphInstance.current = instance;
    instance.on("tap", "node, edge", (event) => setSelected(event.target.data() as Record<string, unknown>));
    return () => {
      graphInstance.current = null;
      instance.destroy();
    };
  }, [graph]);
  useEffect(() => {
    const instance = graphInstance.current;
    if (!instance) return;
    const term = search.trim().toLocaleLowerCase();
    instance.elements().removeClass("dim");
    if (!term) return;
    const matchingNodes = instance.nodes().filter((node) =>
      `${String(node.data("label") ?? "")} ${node.id()}`.toLocaleLowerCase().includes(term),
    );
    const visible = matchingNodes.union(matchingNodes.connectedEdges());
    instance.elements().difference(visible).addClass("dim");
  }, [search]);
  return (
    <div className="graph-page">
      <ViewHeader eyebrow="Knowledge graph" title="ナレッジグラフ" description="設計要素、relation、evidenceの接続を確認します。" />
      <div className="graph-workspace">
        <section className="graph-stage"><div className="graph-tools"><label className="search-control"><Search size={15} /><input id="graph-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ノードを検索" /></label></div>{graph?.nodes.length ? <div id="graph-canvas" ref={container} aria-label="設計要素と関係を表示するknowledge graph" /> : <EmptyState icon={Network} title="グラフがありません" body="設計書を取り込むとグラフが表示されます。" />}</section>
        <aside className="graph-inspector">{selected ? <><p className="eyebrow">Selection</p><h2>{String(selected.label ?? selected.id)}</h2><dl className="property-list">{Object.entries(selected).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{Array.isArray(value) ? value.join(", ") : String(value)}</dd></div>)}</dl></> : <EmptyState icon={CircleDot} title="要素を選択" body="ノードまたはrelationを選択すると詳細を表示します。" compact />}</aside>
      </div>
    </div>
  );
}

function AliasesView({ aliases }: { aliases: AliasData | null }) {
  const candidates = aliases?.candidates ?? [];
  return <div className="page"><ViewHeader eyebrow="Review queue" title="Aliasレビュー" description="同一概念の候補を根拠と周辺relationで確認します。" /><section className="data-list">{candidates.length ? candidates.map((candidate, index) => <article className="data-row" key={String(candidate.candidate_id ?? index)}><div><div className="tag-row"><StatusTag value={String(candidate.judgement ?? "unsure")} /><StatusTag value={String(candidate.status ?? "pending")} /></div><h2>{String(candidate.entity_a_id ?? candidate.target_id ?? "Entity")}</h2><p><ArrowRight size={14} /> {String(candidate.entity_b_id ?? (candidate.aliases as string[] | undefined)?.join(", ") ?? "Alias")}</p></div><small>{String(candidate.llm_reason ?? candidate.reason ?? "根拠を確認してください")}</small></article>) : <EmptyState icon={GitCompareArrows} title="Alias候補はありません" body="候補生成後にここへ表示されます。" />}</section></div>;
}

function JobsView({ jobs }: { jobs: Job[] }) {
  return <div className="page"><ViewHeader eyebrow="Operations" title="ジョブと監査" description="案件内の更新処理は順番に実行されます。" /><section className="table-panel"><table className="jobs-table"><thead><tr><th>Action</th><th>State</th><th>Input</th><th>Created</th><th>Finished</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.job_id}><td><strong>{job.action}</strong><small>{job.job_id.slice(0, 10)}</small></td><td><StatusTag value={job.state} /></td><td>{job.input_kind}</td><td>{formatDate(job.created_at)}</td><td>{job.finished_at ? formatDate(job.finished_at) : "—"}</td></tr>)}</tbody></table>{!jobs.length && <EmptyState icon={ListChecks} title="ジョブ履歴はありません" body="更新処理を実行すると履歴が保存されます。" />}</section></div>;
}

function SettingsView({ overview }: { overview: Overview | null }) {
  return <div className="page"><ViewHeader eyebrow="System" title="設定とプライバシー" description="現在の案件設定と外部送信状態を確認します。" /><div className="settings-grid"><section className="section-panel"><div className="section-heading"><span><Bolt size={17} />LLM provider</span></div><dl className="settings-list"><div><dt>Enabled</dt><dd>{overview?.llm.enabled ? "Yes" : "No"}</dd></div><div><dt>Provider</dt><dd>{overview?.llm.provider ?? "Local fallback"}</dd></div><div><dt>Model</dt><dd>{overview?.llm.model ?? "—"}</dd></div><div><dt>External transmission</dt><dd>{overview?.llm.external_transmission ? "Job approval required" : "None"}</dd></div></dl></section><section className="section-panel"><div className="section-heading"><span><Database size={17} />Storage</span></div><dl className="settings-list"><div><dt>Backend</dt><dd>local JSONL</dd></div><div><dt>Project path</dt><dd><code>{overview?.project.path}</code></dd></div><div><dt>Latest run</dt><dd><code>{overview?.latest_run ?? "none"}</code></dd></div></dl></section><section className="section-panel privacy-panel"><div className="section-heading"><span><ShieldCheck size={17} />Privacy doctor</span></div><pre>{overview?.privacy_doctor}</pre></section></div></div>;
}

function EmptyState({ icon: Icon, title, body, compact = false }: { icon: typeof FileText; title: string; body: string; compact?: boolean }) {
  return <div className={`empty-state ${compact ? "compact" : ""}`}><Icon size={compact ? 22 : 28} /><strong>{title}</strong><p>{body}</p></div>;
}

function LoadingState({ label }: { label: string }) {
  return <div className="loading-state"><LoaderCircle className="spin" size={24} /><span>{label}</span></div>;
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="error-banner" role="alert"><AlertTriangle size={18} /><span>{message}</span><button onClick={onRetry}>再試行</button></div>;
}

function NoProject() {
  return <div className="no-project"><FileSearch size={34} /><h1>案件が登録されていません</h1><p><code>specimpact gui --project C:\path\to\project</code>で案件を登録して起動してください。</p></div>;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("ja-JP", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function formatTransmissionPreview(transmissions: Array<Record<string, unknown>>): string {
  const details = transmissions.map((item) => `${String(item.provider ?? "provider")} / ${String(item.model ?? "model")} / ${String(item.purpose ?? "analysis")} / ${String(item.item_count_label ?? item.item_count ?? "件数未確定")}`).join("\n");
  return `外部LLMへ次のデータを送信します。\n\n${details}\n\nこのジョブを実行しますか？`;
}

async function waitForJob(projectId: string, jobId: string): Promise<Job> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await api.job(projectId, jobId);
    if (TERMINAL_STATES.has(job.state)) {
      if (job.state !== "succeeded") throw new Error(job.error_summary ?? `Job ${job.state}`);
      return job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error("分析ジョブがタイムアウトしました。");
}
