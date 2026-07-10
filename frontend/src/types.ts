export type ViewName = "dashboard" | "sources" | "impact-board" | "graph" | "aliases" | "jobs" | "settings";

export interface Project {
  project_id: string;
  path: string;
  display_name: string;
}

export interface Overview {
  project: Project;
  initialized: boolean;
  counts: Record<string, number>;
  latest_run: string | null;
  privacy_doctor: string;
  llm: {
    enabled: boolean;
    provider: string | null;
    model: string | null;
    external_transmission: boolean;
  };
  backend: string | Record<string, unknown>;
  embeddings: Record<string, unknown>;
  dirty_excel: Record<string, unknown> | null;
}

export interface EvidenceSummary {
  evidence_id: string;
  quote: string;
  source_location: {
    file: string;
    line_start: number;
    line_end: number;
  };
}

export interface Impact {
  artifact_id: string;
  display_name: string;
  artifact_type: string;
  review_priority: string;
  evidence_strength: string;
  match_type?: string;
  relation_distance?: number;
  rule_assessment?: string;
  needs_review?: boolean;
  reason: string;
  relation_paths: string[];
  evidence_ids: string[];
  evidence?: EvidenceSummary[];
  relation_statuses?: string[];
  impact_type?: string;
  required_actions?: string[];
  warnings?: string[];
  llm_reason?: string;
  uncertainty?: string;
}

export interface Report {
  run_id: string;
  change: {
    change_id: string;
    title: string;
    path: string;
    changed_entity_ids: string[];
  };
  must_review: Impact[];
  should_review: Impact[];
  may_review: Impact[];
  hidden: Impact[];
}

export interface DesignRow {
  line: number;
  text: string;
  highlight: boolean;
  evidence_ids: string[];
}

export interface DesignCell {
  sheet_name: string;
  cell: string;
  value: string | null;
  merged_range: string | null;
  highlight: boolean;
  evidence_ids: string[];
}

export interface DesignDocument {
  document_id: string | null;
  title: string;
  file: string;
  document_type: string;
  highlight_count: number;
  evidence_count: number;
  evidence: EvidenceSummary[];
  rows: DesignRow[];
  cells: DesignCell[];
}

export interface DesignDocuments {
  selected_evidence_ids: string[];
  documents: DesignDocument[];
}

export interface SourceSummary {
  source_id: string;
  title: string;
  path: string;
  source_type: string;
  loaded_at: string | null;
  evidence_count: number;
  artifact_count: number;
  relation_count: number;
  sheet_count: number;
  region_count: number;
  warnings: string[];
  status: string;
}

export interface GraphData {
  nodes: Array<{ data: Record<string, unknown> & { id: string; label: string } }>;
  edges: Array<{
    data: Record<string, unknown> & {
      id: string;
      source: string;
      target: string;
      label: string;
      status: string;
      evidence_ids: string[];
    };
  }>;
}

export interface Job {
  job_id: string;
  action: string;
  state: string;
  input_kind: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
}

export interface AliasData {
  aliases: Record<string, unknown>;
  suggestions: Array<Record<string, unknown>>;
  candidates: Array<Record<string, unknown>>;
}
