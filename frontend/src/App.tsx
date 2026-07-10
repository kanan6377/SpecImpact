import cytoscape from "cytoscape";
import {
  AlertTriangle,
  Bolt,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  ClipboardCheck,
  Database,
  FileSearch,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  Network,
  PanelRightOpen,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import type {
  DesignDocument,
  DesignDocuments,
  GraphData,
  Impact,
  Job,
  Overview,
  Project,
  Report,
  ReviewItem,
  ReviewQueue,
  SourceSummary,
  ViewName,
} from "./types";

const VIEWS: Array<{ id: ViewName; label: string; icon: typeof LayoutDashboard }> = [
  { id: "dashboard", label: "概要", icon: LayoutDashboard },
  { id: "sources", label: "設計書", icon: FolderOpen },
  { id: "impact-board", label: "変更レビュー", icon: Bolt },
  { id: "graph", label: "ナレッジグラフ", icon: Network },
  { id: "reviews", label: "レビュー", icon: ClipboardCheck },
  { id: "jobs", label: "ジョブと監査", icon: ListChecks },
  { id: "settings", label: "設定", icon: Settings },
];

const WORKSPACE_VIEWS = VIEWS.filter((view) => ["dashboard", "sources", "impact-board", "graph", "reviews"].includes(view.id));
const SYSTEM_VIEWS = VIEWS.filter((view) => ["jobs", "settings"].includes(view.id));

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

function updateReviewUrl(projectId: string, impactId: string, sourceId: string, evidenceId = ""): void {
  const params = new URLSearchParams();
  params.set("project_id", projectId);
  if (impactId) params.set("impact", impactId);
  if (sourceId) params.set("source", sourceId);
  if (evidenceId) params.set("evidence", evidenceId);
  window.history.replaceState({}, "", `/ui/impact-board?${params.toString()}`);
}

function reviewParam(name: string): string {
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

export function App() {
  const [view, setView] = useState<ViewName>(currentView);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(projectIdFromUrl);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [design, setDesign] = useState<DesignDocuments | null>(null);
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [reviews, setReviews] = useState<ReviewQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadProject = useCallback(async (nextProjectId: string) => {
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      api.overview(nextProjectId),
      api.report(nextProjectId),
      api.graph(nextProjectId),
      api.jobs(nextProjectId),
      api.designDocuments(nextProjectId),
      api.sources(nextProjectId),
      api.reviews(nextProjectId),
    ]);
    const [overviewResult, reportResult, graphResult, jobsResult, designResult, sourcesResult, reviewsResult] = results;
    if (overviewResult.status === "rejected") {
      setError(overviewResult.reason instanceof Error ? overviewResult.reason.message : "案件を読み込めませんでした");
      setLoading(false);
      return;
    }
    setOverview(overviewResult.value);
    setReport(reportResult.status === "fulfilled" ? reportResult.value : null);
    setGraph(graphResult.status === "fulfilled" ? graphResult.value : null);
    setJobs(jobsResult.status === "fulfilled" ? jobsResult.value.jobs : []);
    setDesign(designResult.status === "fulfilled" ? designResult.value : null);
    setSources(sourcesResult.status === "fulfilled" ? sourcesResult.value.sources : []);
    setReviews(reviewsResult.status === "fulfilled" ? reviewsResult.value : null);
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
      if (requested !== selected.project_id) updateUrl(currentView(), selected.project_id, true);
      await loadProject(selected.project_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "GUIを初期化できませんでした");
      setLoading(false);
    }
  }, [loadProject]);

  useEffect(() => { void bootstrap(); }, [bootstrap]);

  useEffect(() => {
    const onPopState = () => {
      setView(currentView());
      const nextProjectId = projectIdFromUrl();
      if (nextProjectId) {
        setProjectId(nextProjectId);
        void loadProject(nextProjectId);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [loadProject]);

  const navigate = (nextView: ViewName) => {
    setView(nextView);
    updateUrl(nextView, projectId);
  };

  const selectProject = (nextProjectId: string) => {
    setProjectId(nextProjectId);
    updateUrl(view, nextProjectId, true);
    void loadProject(nextProjectId);
  };

  const refresh = async () => { if (projectId) await loadProject(projectId); };

  const activateProject = async (project: Project) => {
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
    setProjectId(project.project_id);
    setView("dashboard");
    updateUrl("dashboard", project.project_id, true);
    await loadProject(project.project_id);
  };

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
          {!error && !loading && !projectId && <NoProject onProjectCreated={activateProject} />}
          {!error && !loading && projectId && (
            <ActiveView
              view={view}
              projectId={projectId}
              overview={overview}
              report={report}
              graph={graph}
              jobs={jobs}
              design={design}
              sources={sources}
              reviews={reviews}
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
        {WORKSPACE_VIEWS.map(({ id, label, icon: Icon }) => (
          <button key={id} className={view === id ? "active" : ""} onClick={() => onNavigate(id)} aria-current={view === id ? "page" : undefined}>
            <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
          </button>
        ))}
        <p className="nav-label">System</p>
        {SYSTEM_VIEWS.map(({ id, label, icon: Icon }) => (
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
  jobs: Job[];
  design: DesignDocuments | null;
  sources: SourceSummary[];
  reviews: ReviewQueue | null;
  onDesignChange: (design: DesignDocuments) => void;
  onRefresh: () => Promise<void>;
  onNavigate: (view: ViewName) => void;
}) {
  if (props.view === "dashboard") return <Dashboard overview={props.overview} report={props.report} jobs={props.jobs} onNavigate={props.onNavigate} />;
  if (props.view === "sources") return <SourceLibrary projectId={props.projectId} overview={props.overview} sources={props.sources} onRefresh={props.onRefresh} />;
  if (props.view === "impact-board") return <ImpactWorkspace {...props} />;
  if (props.view === "graph") return <GraphView graph={props.graph} />;
  if (props.view === "reviews") return <ReviewQueueView projectId={props.projectId} queue={props.reviews} onRefresh={props.onRefresh} />;
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
            <div className="empty-inline"><FolderOpen size={20} /><span>分析runがありません。最初に設計書を追加してください。</span><button className="secondary-button" onClick={() => onNavigate("sources")}>設計書を開く</button></div>
          )}
          <button className="next-action-row" onClick={() => onNavigate("reviews")}>
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

type SourceMode = "docs" | "dirty_excel" | "openapi" | "ddl" | "csv";

const SOURCE_MODES: Record<SourceMode, { label: string; accept: string; workflow: string; action: string }> = {
  docs: { label: "文書", accept: ".md,.txt", workflow: "docs", action: "ingest" },
  dirty_excel: { label: "Dirty Excel", accept: ".xlsx", workflow: "table", action: "ingest_dirty_excel" },
  openapi: { label: "OpenAPI", accept: ".yaml,.yml,.json", workflow: "openapi", action: "ingest_openapi" },
  ddl: { label: "DDL", accept: ".sql", workflow: "ddl", action: "ingest_ddl" },
  csv: { label: "CSV", accept: ".csv", workflow: "table", action: "ingest_csv" },
};

function SourceLibrary({ projectId, overview, sources, onRefresh }: {
  projectId: string;
  overview: Overview | null;
  sources: SourceSummary[];
  onRefresh: () => Promise<void>;
}) {
  const [mode, setMode] = useState<SourceMode>("dirty_excel");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const addSources = async () => {
    if (!files.length) {
      setMessage("追加する設計書を選択してください。");
      return;
    }
    setBusy(true);
    setMessage("設計書を案件内へ保存しています…");
    try {
      if (!overview?.initialized) {
        const initialized = await api.enqueue(projectId, "init", {}, false, "settings");
        await waitForJob(projectId, initialized.job.job_id);
      }
      const definition = SOURCE_MODES[mode];
      const uploaded = await api.upload(projectId, definition.workflow, files);
      const targets = mode === "docs" || mode === "dirty_excel"
        ? [parentPath(uploaded.paths[0])]
        : uploaded.paths;
      for (const path of targets) {
        const params: Record<string, unknown> = { path };
        if (mode === "dirty_excel") params.llm = true;
        if (mode === "docs") params.no_llm = false;
        const preview = await api.externalPreview(projectId, definition.action, params);
        const approved = !preview.required || window.confirm(formatTransmissionPreview(preview.transmissions));
        if (!approved) throw new Error("外部送信を承認しなかったため、取り込みを中止しました。");
        const created = await api.enqueue(projectId, definition.action, params, approved, "upload");
        await waitForJob(projectId, created.job.job_id);
      }
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      setMessage(`${uploaded.paths.length}件の設計書を取り込みました。`);
      await onRefresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "設計書を取り込めませんでした");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page page-sources">
      <ViewHeader eyebrow="Design sources" title="設計書" description="案件へ保存した原本と、evidence graphへの取り込み状態を確認します。" />
      <section className="source-import section-panel" aria-label="設計書を追加">
        <div className="source-mode" aria-label="設計書の種類">
          {(Object.entries(SOURCE_MODES) as Array<[SourceMode, typeof SOURCE_MODES[SourceMode]]>).map(([key, item]) => (
            <button type="button" key={key} className={mode === key ? "active" : ""} onClick={() => { setMode(key); setFiles([]); }}>{item.label}</button>
          ))}
        </div>
        <label className="file-picker">
          <Upload size={18} />
          <span><strong>{files.length ? `${files.length}件を選択中` : "ファイルを選択"}</strong><small>{SOURCE_MODES[mode].accept} · 原本は案件内に保存されます</small></span>
          <input ref={inputRef} type="file" accept={SOURCE_MODES[mode].accept} multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
        </label>
        <button className="primary-button" type="button" onClick={() => void addSources()} disabled={busy || !files.length}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}取り込む
        </button>
      </section>
      {message && <p className="form-message" role="status">{message}</p>}
      <section className="source-library section-panel">
        <div className="section-heading"><span><FolderOpen size={17} />Source Library</span><small>{sources.length} sources</small></div>
        {sources.length ? <div className="source-list">{sources.map((source) => <article className="source-item" key={source.source_id}>
          <div className="source-icon">{source.source_type.includes("excel") ? <FileSpreadsheet size={19} /> : <FileText size={19} />}</div>
          <div className="source-copy"><strong>{source.title}</strong><small title={source.path}>{source.path}</small></div>
          <StatusTag value={source.stale_count > 0 ? "stale" : source.status} />
          <dl className="source-facts"><div><dt>Version</dt><dd>{source.version_count}</dd></div><div><dt>Evidence</dt><dd>{source.evidence_count}</dd></div><div><dt>Artifacts</dt><dd>{source.artifact_count}</dd></div><div><dt>Relations</dt><dd>{source.relation_count}</dd></div>{source.sheet_count > 0 && <div><dt>Sheets</dt><dd>{source.sheet_count}</dd></div>}</dl>
          {(source.warnings.length > 0 || source.stale_count > 0) && <span className="source-warning" title={[...source.warnings, source.stale_count ? `${source.stale_count} stale records` : ""].filter(Boolean).join("\n")}><AlertTriangle size={15} />{source.warnings.length + source.stale_count}</span>}
        </article>)}</div> : <EmptyState icon={FolderOpen} title="設計書はまだありません" body="上の追加欄から文書、Dirty Excel、OpenAPI、DDL、CSVを取り込めます。" />}
      </section>
    </div>
  );
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
  onRefresh: () => Promise<void>;
}) {
  const impacts = useMemo(() => groupedImpacts(report).filter((impact) => impact.priority !== "hidden"), [report]);
  const initialReview = useRef({ impact: reviewParam("impact"), source: reviewParam("source"), evidence: reviewParam("evidence") }).current;
  const [selectedImpactId, setSelectedImpactId] = useState(() => initialReview.impact || impacts[0]?.artifact_id || "");
  const [selectedDocument, setSelectedDocument] = useState("");
  const [focusedEvidenceId, setFocusedEvidenceId] = useState(initialReview.evidence);
  const [selectionReady, setSelectionReady] = useState(false);
  const [query, setQuery] = useState("");
  const [changeText, setChangeText] = useState("");
  const [analysisState, setAnalysisState] = useState<"idle" | "running">("idle");
  const [message, setMessage] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(true);

  useEffect(() => {
    if (selectionReady || !design) return;
    const requestedDocument = design.documents.find((document) => (document.document_id ?? document.file) === initialReview.source);
    setSelectedDocument(requestedDocument?.file ?? design.documents[0]?.file ?? "");
    if (!impacts.some((impact) => impact.artifact_id === selectedImpactId)) {
      setSelectedImpactId(impacts[0]?.artifact_id ?? "");
    }
    setSelectionReady(true);
  }, [design, impacts, initialReview.source, selectedImpactId, selectionReady]);

  useEffect(() => {
    if (!impacts.length) return;
    if (!impacts.some((impact) => impact.artifact_id === selectedImpactId)) {
      setSelectedImpactId(impacts[0].artifact_id);
    }
  }, [impacts, selectedImpactId]);

  useEffect(() => {
    if (selectionReady && design?.documents[0] && !design.documents.some((item) => item.file === selectedDocument)) {
      setSelectedDocument(design.documents[0].file);
    }
  }, [design, selectedDocument, selectionReady]);

  const selectedImpact = impacts.find((impact) => impact.artifact_id === selectedImpactId) ?? impacts[0];
  const selectedDoc = design?.documents.find((document) => document.file === selectedDocument) ?? design?.documents[0];

  useEffect(() => {
    if (!selectionReady || !selectedImpact || !selectedDoc) return;
    updateReviewUrl(
      projectId,
      selectedImpact.artifact_id,
      selectedDoc.document_id ?? selectedDoc.file,
      focusedEvidenceId,
    );
  }, [focusedEvidenceId, projectId, selectedDoc, selectedImpact, selectionReady]);

  const selectImpact = async (impact: RankedImpact) => {
    setSelectedImpactId(impact.artifact_id);
    try {
      const nextDesign = await api.designDocuments(projectId, impact.evidence_ids);
      onDesignChange(nextDesign);
      const highlighted = nextDesign.documents.find((document) => document.highlight_count > 0);
      const nextDocument = highlighted ?? nextDesign.documents[0];
      setSelectedDocument(nextDocument?.file ?? "");
      setFocusedEvidenceId("");
      updateReviewUrl(projectId, impact.artifact_id, nextDocument?.document_id ?? nextDocument?.file ?? "");
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
    const params = { body: changeText.trim(), design_document: selectedDoc?.document_id ?? selectedDocument };
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
      await onRefresh();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "分析に失敗しました。");
    } finally {
      setAnalysisState("idle");
    }
  };

  const selectDocument = (file: string) => {
    setSelectedDocument(file);
    setFocusedEvidenceId("");
    const document = design?.documents.find((item) => item.file === file);
    updateReviewUrl(projectId, selectedImpact?.artifact_id ?? "", document?.document_id ?? file);
  };

  const revealEvidence = (evidenceId: string) => {
    const document = design?.documents.find((item) => item.evidence.some((evidence) => evidence.evidence_id === evidenceId));
    if (document) setSelectedDocument(document.file);
    setFocusedEvidenceId(evidenceId);
    updateReviewUrl(projectId, selectedImpact?.artifact_id ?? "", document?.document_id ?? document?.file ?? selectedDocument, evidenceId);
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
          <label><span>起点となる設計書</span><select value={selectedDocument} onChange={(event) => selectDocument(event.target.value)}><option value="">案件全体</option>{design?.documents.map((document) => <option value={document.file} key={document.file}>{document.title}</option>)}</select></label>
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
            <div className="pane-toolbar source-toolbar"><div><FileText size={16} /><strong>{selectedDoc?.title ?? "設計書"}</strong></div>{selectedDoc && <select value={selectedDoc.file} onChange={(event) => selectDocument(event.target.value)}>{design?.documents.map((document) => <option value={document.file} key={document.file}>{document.title} ({document.highlight_count})</option>)}</select>}</div>
            <DocumentViewer document={selectedDoc} focusedEvidenceId={focusedEvidenceId} />
          </section>
        </div>
      </section>
      {inspectorOpen && <ImpactInspector impact={selectedImpact} onClose={() => setInspectorOpen(false)} onRevealEvidence={revealEvidence} />}
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

function DocumentViewer({ document, focusedEvidenceId }: { document: DesignDocument | undefined; focusedEvidenceId: string }) {
  const viewer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!focusedEvidenceId || !viewer.current) return;
    const target = Array.from(viewer.current.querySelectorAll<HTMLElement>("[data-evidence-ids]")).find((element) =>
      (element.dataset.evidenceIds ?? "").split(" ").includes(focusedEvidenceId),
    );
    target?.scrollIntoView({ block: "center" });
  }, [document?.file, focusedEvidenceId]);
  if (!document) return <EmptyState icon={FileText} title="設計書がありません" body="この案件には表示可能な設計書がありません。" />;
  if (document.cells.length) {
    return <div className="document-scroll" ref={viewer}><table className="cell-table"><thead><tr><th>Sheet</th><th>Cell</th><th>Value</th></tr></thead><tbody>{document.cells.map((cell) => <tr key={`${cell.sheet_name}-${cell.cell}`} data-evidence-ids={cell.evidence_ids.join(" ")} className={`${cell.highlight ? "highlight" : ""} ${cell.evidence_ids.includes(focusedEvidenceId) ? "evidence-focus" : ""}`}><td>{cell.sheet_name}</td><td><code>{cell.cell}</code>{cell.merged_range && <small>{cell.merged_range}</small>}</td><td>{cell.value}</td></tr>)}</tbody></table></div>;
  }
  if (document.rows.length) {
    return <div className="document-scroll source-code" ref={viewer}>{document.rows.map((row) => <div data-evidence-ids={row.evidence_ids.join(" ")} className={`source-row ${row.highlight ? "highlight" : ""} ${row.evidence_ids.includes(focusedEvidenceId) ? "evidence-focus" : ""}`} key={row.line}><span>{row.line}</span><code>{row.text || " "}</code></div>)}</div>;
  }
  return <div className="document-scroll evidence-fallback" ref={viewer}>{document.evidence.map((evidence) => <article data-evidence-ids={evidence.evidence_id} className={evidence.evidence_id === focusedEvidenceId ? "evidence-focus" : ""} key={evidence.evidence_id}><code>{evidence.evidence_id}</code><p>{evidence.quote}</p></article>)}</div>;
}

function ImpactInspector({ impact, onClose, onRevealEvidence }: { impact: RankedImpact | undefined; onClose: () => void; onRevealEvidence: (evidenceId: string) => void }) {
  if (!impact) return <aside className="inspector"><button className="inspector-close icon-button" onClick={onClose} title="Inspectorを閉じる" aria-label="Inspectorを閉じる"><X size={17} /></button><EmptyState icon={FileSearch} title="候補を選択" body="候補を選ぶと根拠と経路を表示します。" compact /></aside>;
  return (
    <aside className="inspector" aria-label="Evidence Inspector">
      <div className="inspector-title"><button className="inspector-close icon-button" onClick={onClose} title="Inspectorを閉じる" aria-label="Inspectorを閉じる"><X size={17} /></button><p className="eyebrow">Evidence inspector</p><h2>{impact.display_name}</h2><div className="tag-row"><StatusTag value={impact.priority} /><StatusTag value={impact.evidence_strength} /><StatusTag value={impact.artifact_type} /></div></div>
      <InspectorSection title="Reason"><p>{impact.reason}</p></InspectorSection>
      <InspectorSection title="Verification"><dl className="verification-list"><div><dt>Match</dt><dd>{impact.match_type ?? "—"}</dd></div><div><dt>Rule</dt><dd>{impact.rule_assessment ?? "—"}</dd></div><div><dt>Distance</dt><dd>{impact.relation_distance ?? "—"}</dd></div><div><dt>Relation status</dt><dd>{impact.relation_statuses?.join(", ") || "—"}</dd></div></dl></InspectorSection>
      <InspectorSection title="Relation path">{impact.relation_paths.map((path) => <code className="path-code" key={path}>{path}</code>)}</InspectorSection>
      <InspectorSection title="Required actions"><ul>{(impact.required_actions ?? []).map((action) => <li key={action}>{action}</li>)}</ul></InspectorSection>
      <InspectorSection title="Evidence">{impact.evidence?.map((evidence) => <button type="button" className="evidence-block" key={evidence.evidence_id} onClick={() => onRevealEvidence(evidence.evidence_id)}><code>{evidence.evidence_id}</code><small>{evidence.source_location.file} · L{evidence.source_location.line_start}</small><span>{evidence.quote}</span></button>)}</InspectorSection>
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
        { selector: 'node[stale = true]', style: { "border-color": "#dc2626", "border-width": 4 } },
        { selector: 'edge[stale = true]', style: { "line-color": "#dc2626", "target-arrow-color": "#dc2626", "line-style": "dashed", width: 3 } },
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

const REVIEW_KIND_LABELS: Record<string, string> = {
  graph_diff: "Graph diff",
  graph_proposal: "Graph proposal",
  unresolved_mention: "未解決参照",
  alias: "Alias",
  relation: "Relation",
  impact: "Impact",
};

const IMPACT_STATUSES = ["unreviewed", "accepted", "rejected", "needs_investigation", "implemented", "tested", "closed"];

function ReviewQueueView({ projectId, queue, onRefresh }: { projectId: string; queue: ReviewQueue | null; onRefresh: () => Promise<void> }) {
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("actionable");
  const [selectedId, setSelectedId] = useState(() => reviewParam("review"));
  const [decisionStatus, setDecisionStatus] = useState("unreviewed");
  const [decisionReason, setDecisionReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const items = queue?.items ?? [];
  const actionable = new Set(["pending", "unreviewed", "unconfirmed", "needs_investigation", "stale"]);
  const filtered = items.filter((item) => (kind === "all" || item.kind === kind) && (status === "all" || (status === "actionable" ? actionable.has(item.status) : item.status === status)));
  const selected = filtered.find((item) => item.item_id === selectedId) ?? filtered[0];

  useEffect(() => {
    if (!selected) return;
    if (selected.item_id !== selectedId) setSelectedId(selected.item_id);
    const params = new URLSearchParams(window.location.search);
    params.set("project_id", projectId);
    params.set("review", selected.item_id);
    params.set("kind", kind);
    params.set("status", status);
    window.history.replaceState({}, "", `/ui/reviews?${params.toString()}`);
  }, [kind, projectId, selected, selectedId, status]);

  useEffect(() => {
    if (selected?.kind !== "impact") return;
    setDecisionStatus(selected.status);
    setDecisionReason(String(selected.metadata.decision_reason ?? ""));
  }, [selected]);

  const runDecision = async (action: string, params: Record<string, unknown>) => {
    setBusy(true);
    setMessage("判断を保存しています…");
    try {
      const created = await api.enqueue(projectId, action, params, false, "settings");
      await waitForJob(projectId, created.job.job_id);
      await onRefresh();
      setMessage("判断を保存しました。");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "判断を保存できませんでした");
    } finally {
      setBusy(false);
    }
  };

  return <div className="page page-reviews">
    <ViewHeader eyebrow="Unified review queue" title="レビュー" description="Graph proposal、Alias、relation、Impactを根拠と同じ画面で判断します。" />
    <section className="review-summary" aria-label="レビュー件数"><div><span>Actionable</span><strong>{queue?.summary.actionable ?? 0}</strong></div><div><span>Total</span><strong>{queue?.summary.total ?? 0}</strong></div>{Object.entries(queue?.summary.by_kind ?? {}).map(([key, count]) => <div key={key}><span>{REVIEW_KIND_LABELS[key] ?? key}</span><strong>{count}</strong></div>)}</section>
    <div className="review-filters"><div className="source-mode" aria-label="レビュー種類"><button className={kind === "all" ? "active" : ""} onClick={() => setKind("all")}>すべて</button>{Object.entries(REVIEW_KIND_LABELS).map(([key, label]) => <button key={key} className={kind === key ? "active" : ""} onClick={() => setKind(key)}>{label}</button>)}</div><label>状態<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="actionable">要確認</option><option value="all">すべて</option><option value="stale">stale</option><option value="accepted">accepted</option><option value="rejected">rejected</option><option value="confirmed">confirmed</option><option value="reviewed">reviewed</option><option value="closed">closed</option></select></label></div>
    {message && <p className="form-message" role="status">{message}</p>}
    <section className="unified-review section-panel">
      <div className="review-list" aria-label="レビュー項目">{filtered.length ? filtered.map((item) => <button type="button" className={`review-row ${selected?.item_id === item.item_id ? "selected" : ""}`} key={item.item_id} onClick={() => setSelectedId(item.item_id)}><span className={`priority-dot ${item.priority}`} /><span><small>{REVIEW_KIND_LABELS[item.kind]}</small><strong>{item.title}</strong><em>{item.subtitle}</em></span><StatusTag value={item.status} /></button>) : <EmptyState icon={ClipboardCheck} title="該当するレビューはありません" body="filterを変更するか、設計書を取り込んでください。" compact />}</div>
      <div className="review-detail">{selected ? <>
        <header><div><p className="eyebrow">{REVIEW_KIND_LABELS[selected.kind]}</p><h2>{selected.title}</h2><p>{selected.subtitle}</p></div><div className="tag-row"><StatusTag value={selected.priority} /><StatusTag value={selected.status} /></div></header>
        <section><h3>Reason</h3><p>{selected.reason}</p></section>
        {selected.kind === "graph_diff" && <ReviewMetadata title="Relation diff" metadata={selected.metadata} keys={["transaction_id", "document_ids", "added_relation_ids", "removed_relation_ids", "changed_relation_ids", "created_at"]} />}
        {selected.kind === "graph_proposal" && <ProposalDiff metadata={selected.metadata} />}
        {selected.kind === "alias" && <ReviewMetadata title="Comparison" metadata={selected.metadata} keys={["judgement", "aliases", "relation_context", "surrounding_node_ids"]} />}
        {selected.kind === "relation" && <ReviewMetadata title="Relation" metadata={selected.metadata} keys={["source_id", "target_id", "extraction_method", "polarity", "match_type"]} />}
        {selected.kind === "impact" && <ReviewMetadata title="Impact hypothesis" metadata={selected.metadata} keys={["change_id", "impact_type", "required_actions", "warnings", "updated_at"]} />}
        <section><h3>Evidence</h3>{selected.evidence.length ? selected.evidence.map((evidence) => <article className="review-evidence" key={evidence.evidence_id}><code>{evidence.evidence_id}</code><small>{evidence.source_location.file} · L{evidence.source_location.line_start}</small><p>{evidence.quote}</p></article>) : <p className="muted">参照可能なevidenceはありません。</p>}</section>
        <section className="review-decision"><h3>Decision</h3><ReviewDecision item={selected} busy={busy} decisionStatus={decisionStatus} decisionReason={decisionReason} onStatusChange={setDecisionStatus} onReasonChange={setDecisionReason} onRun={runDecision} /></section>
      </> : <EmptyState icon={ClipboardCheck} title="レビュー項目を選択" body="左のqueueから項目を選んでください。" />}</div>
    </section>
  </div>;
}

function ProposalDiff({ metadata }: { metadata: Record<string, unknown> }) {
  const nodes = Array.isArray(metadata.nodes) ? metadata.nodes as Array<Record<string, unknown>> : [];
  const edges = Array.isArray(metadata.edges) ? metadata.edges as Array<Record<string, unknown>> : [];
  return <section><h3>Graph diff preview</h3><div className="proposal-columns"><div><strong>追加node · {nodes.length}</strong>{nodes.map((node, index) => <p key={`${String(node.id)}-${index}`}><code>{String(node.type)}</code>{String(node.name)}</p>)}</div><div><strong>追加edge · {edges.length}</strong>{edges.map((edge, index) => <p key={`${String(edge.source)}-${index}`}><code>{String(edge.relation)}</code>{String(edge.source)} → {String(edge.target)}</p>)}</div></div></section>;
}

function ReviewMetadata({ title, metadata, keys }: { title: string; metadata: Record<string, unknown>; keys: string[] }) {
  return <section><h3>{title}</h3><dl className="review-metadata">{keys.map((key) => <div key={key}><dt>{key}</dt><dd>{formatMetadata(metadata[key])}</dd></div>)}</dl></section>;
}

function ReviewDecision({ item, busy, decisionStatus, decisionReason, onStatusChange, onReasonChange, onRun }: {
  item: ReviewItem;
  busy: boolean;
  decisionStatus: string;
  decisionReason: string;
  onStatusChange: (status: string) => void;
  onReasonChange: (reason: string) => void;
  onRun: (action: string, params: Record<string, unknown>) => Promise<void>;
}) {
  if (item.kind === "unresolved_mention") return <p className="muted">参照先を確認後、関連proposalまたはrelationを判断してください。</p>;
  if (item.kind === "graph_diff") return <div className="decision-buttons"><button className="secondary-button danger" disabled={busy} onClick={() => void onRun("graph_diff_decide", { diff_id: item.record_id, status: "ignored", reason: "" })}>Ignore</button><button className="primary-button" disabled={busy} onClick={() => void onRun("graph_diff_decide", { diff_id: item.record_id, status: "reviewed", reason: "reviewed in GUI" })}>Reviewed</button></div>;
  if (item.kind === "graph_proposal") return <div className="decision-buttons"><button className="secondary-button danger" disabled={busy} onClick={() => void onRun("graph_proposal_decide", { proposal_id: item.record_id, status: "rejected" })}>Reject</button><button className="primary-button" disabled={busy} onClick={() => void onRun("graph_proposal_decide", { proposal_id: item.record_id, status: "accepted" })}>Accept</button></div>;
  if (item.kind === "alias") return <div className="decision-buttons"><button className="secondary-button danger" disabled={busy} onClick={() => void onRun("alias_reject_candidate", { candidate_id: item.record_id })}>Reject</button><button className="primary-button" disabled={busy} onClick={() => void onRun("alias_confirm", { candidate_id: item.record_id })}>Confirm same</button></div>;
  if (item.kind === "relation") return <div className="decision-buttons"><button className="secondary-button danger" disabled={busy} onClick={() => void onRun("relation_status", { relation_id: item.record_id, status: "rejected" })}>Reject</button><button className="secondary-button" disabled={busy} onClick={() => void onRun("relation_status", { relation_id: item.record_id, status: "unconfirmed" })}>Reset</button><button className="primary-button" disabled={busy} onClick={() => void onRun("relation_status", { relation_id: item.record_id, status: "confirmed" })}>Confirm</button></div>;
  return <div className="impact-decision-form"><label>状態<select value={decisionStatus} onChange={(event) => onStatusChange(event.target.value)}>{IMPACT_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label>判断理由<textarea value={decisionReason} onChange={(event) => onReasonChange(event.target.value)} placeholder="判断の根拠を記録" /></label><button className="primary-button" disabled={busy} onClick={() => void onRun("impact_status", { impact_id: item.record_id, status: decisionStatus, reason: decisionReason })}>保存</button></div>;
}

function formatMetadata(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(", ") : "—";
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
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

function NoProject({ onProjectCreated }: { onProjectCreated: (project: Project) => Promise<void> }) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const create = async () => {
    if (!path.trim()) {
      setMessage("案件フォルダーを入力してください。");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const response = await api.createProject(path.trim(), name.trim(), true);
      const initialized = await api.enqueue(response.project.project_id, "init", {}, false, "settings");
      await waitForJob(response.project.project_id, initialized.job.job_id);
      await onProjectCreated(response.project);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "案件を作成できませんでした");
    } finally {
      setBusy(false);
    }
  };

  const createDemo = async () => {
    setBusy(true);
    setMessage("");
    try {
      const response = await api.createDemo();
      const run = await api.enqueue(response.project.project_id, "demo_run", {}, false, "demo");
      await waitForJob(response.project.project_id, run.job.job_id);
      await onProjectCreated(response.project);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "サンプルを作成できませんでした");
    } finally {
      setBusy(false);
    }
  };

  return <div className="onboarding">
    <div className="onboarding-heading"><span className="brand-mark" aria-hidden="true">SI</span><p className="eyebrow">Evidence review workspace</p><h1>案件を準備する</h1><p>既存フォルダーを登録するか、新しい案件フォルダーを作成します。設計書と解析データはその案件内に保存されます。</p></div>
    <section className="onboarding-form section-panel">
      <label><span>案件名 <small>任意</small></span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="例: カード入会システム改修" /></label>
      <label><span>案件フォルダー</span><input value={path} onChange={(event) => setPath(event.target.value)} placeholder="C:\\work\\card-application-impact" /></label>
      <button className="primary-button" type="button" onClick={() => void create()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <FolderOpen size={17} />}案件を開始</button>
      <div className="onboarding-divider"><span>or</span></div>
      <button className="secondary-button" type="button" onClick={() => void createDemo()} disabled={busy}><FileText size={17} />ガイド付きサンプルを作成</button>
      {message && <p className="form-message error" role="alert">{message}</p>}
    </section>
    <p className="onboarding-privacy"><ShieldCheck size={15} />GUIは127.0.0.1限定です。外部LLM送信はjobごとにpreviewと承認を要求します。</p>
  </div>;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("ja-JP", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function formatTransmissionPreview(transmissions: Array<Record<string, unknown>>): string {
  const details = transmissions.map((item) => `${String(item.provider ?? "provider")} / ${String(item.model ?? "model")} / ${String(item.purpose ?? "analysis")} / ${String(item.item_count_label ?? item.item_count ?? "件数未確定")}`).join("\n");
  return `外部LLMへ次のデータを送信します。\n\n${details}\n\nこのジョブを実行しますか？`;
}

function parentPath(path: string): string {
  return path.replace(/[\\/][^\\/]+$/, "");
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
