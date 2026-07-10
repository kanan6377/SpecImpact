import type {
  AliasData,
  DesignDocuments,
  GraphData,
  Job,
  Overview,
  Project,
  Report,
  ReviewQueue,
  SourceSummary,
} from "./types";

let csrfToken = "";

async function readError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
  } catch {
    return (await response.text()) || `${response.status} ${response.statusText}`;
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") {
    if (!csrfToken) {
      const session = await request<{ csrf_token: string }>("/api/session");
      csrfToken = session.csrf_token;
    }
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as T;
}

export const api = {
  projects: () => request<{ projects: Project[] }>("/api/projects"),
  createProject: (path: string, displayName: string, create: boolean) =>
    request<{ project: Project }>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ path, display_name: displayName || null, create }),
    }),
  createDemo: () => request<{ project: Project }>("/api/demo", { method: "POST" }),
  overview: (projectId: string) => request<Overview>(`/api/projects/${projectId}/overview`),
  report: (projectId: string) => request<Report>(`/api/projects/${projectId}/report`),
  graph: (projectId: string) => request<GraphData>(`/api/projects/${projectId}/graph`),
  aliases: (projectId: string) => request<AliasData>(`/api/projects/${projectId}/aliases`),
  reviews: (projectId: string) => request<ReviewQueue>(`/api/projects/${projectId}/reviews`),
  jobs: (projectId: string) =>
    request<{ jobs: Job[] }>(`/api/projects/${projectId}/jobs`),
  designDocuments: (projectId: string, evidenceIds: string[] = []) => {
    const query = evidenceIds.map((id) => `evidence_id=${encodeURIComponent(id)}`).join("&");
    return request<DesignDocuments>(
      `/api/projects/${projectId}/design-documents${query ? `?${query}` : ""}`,
    );
  },
  sources: (projectId: string) =>
    request<{ sources: SourceSummary[] }>(`/api/projects/${projectId}/sources`),
  upload: async (projectId: string, workflow: string, files: File[]) => {
    const encoded = await Promise.all(files.map(async (file) => ({
      filename: file.name,
      content_base64: arrayBufferToBase64(await file.arrayBuffer()),
    })));
    return request<{ paths: string[] }>(`/api/projects/${projectId}/uploads`, {
      method: "POST",
      body: JSON.stringify({ workflow, files: encoded }),
    });
  },
  externalPreview: (projectId: string, action: string, params: Record<string, unknown>) =>
    request<{ required: boolean; transmissions: Array<Record<string, unknown>> }>(
      `/api/projects/${projectId}/external-preview?action=${encodeURIComponent(action)}` +
        `&params=${encodeURIComponent(JSON.stringify(params))}`,
    ),
  enqueue: (
    projectId: string,
    action: string,
    params: Record<string, unknown>,
    externalApproved: boolean,
    inputKind: "path" | "upload" | "demo" | "settings" = "settings",
  ) =>
    request<{ job: Job }>(`/api/projects/${projectId}/jobs`, {
      method: "POST",
      body: JSON.stringify({
        action,
        params,
        input_kind: inputKind,
        external_approved: externalApproved,
      }),
    }),
  job: (projectId: string, jobId: string) =>
    request<Job>(`/api/projects/${projectId}/jobs/${jobId}`),
};

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
}
