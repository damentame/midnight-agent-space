const base = "";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json() as Promise<T>;
}

export type Project = {
  project_id: number;
  project_name: string | null;
  project_type: string | null;
  description: string | null;
  status: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Stats = {
  project_count: number;
  task_count: number;
  active_workflow_count: number;
  recent_workflow_runs: {
    workflow_run_id: number;
    workflow_name: string | null;
    project_id: number | null;
    status: string | null;
    started_at?: string | null;
  }[];
};

export type TemporalActivity = {
  scheduled_event_id: number;
  activity_name: string;
  activity_id: string;
  input_summary: string;
  status: string;
  output_summary?: string;
  error?: string;
};

export type TemporalSnapshot = {
  workflow_id: string;
  run_id: string;
  workflow_type: string;
  status: string;
  task_queue?: string;
  history_event_count: number;
  activities: TemporalActivity[];
};

export type TemporalExecutionRow = {
  workflow_id: string;
  run_id: string;
  workflow_type: string;
  status: string;
  start_time: string | null;
  close_time: string | null;
  task_queue: string;
};

export type TemporalTarget = {
  workflow_run_id: number;
  workflow_name: string | null;
  project_id: number | null;
  derived_workflow_id: string | null;
  hint: string;
  input_data: unknown;
};

/** Browser WebSocket URL (via Vite proxy in dev). */
export function wsTemporalExecutionUrl(workflowId: string, runId?: string | null): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return `${proto}//${window.location.host}/ws/temporal/executions/${encodeURIComponent(workflowId)}${q}`;
}

export const api = {
  stats: () => json<Stats>("/api/stats"),
  projects: () => json<Project[]>("/api/projects"),
  project: (id: number) => json<Project>(`/api/projects/${id}`),
  updateProject: (id: number, body: Partial<Project>) =>
    json<Project>(`/api/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  createProject: (body: {
    project_name: string;
    project_type?: string;
    description?: string;
    status?: string;
  }) =>
    json<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  documents: (projectId: number) => json<unknown[]>(`/api/projects/${projectId}/documents`),
  uploadDocument: async (projectId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`/api/projects/${projectId}/documents/upload`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  deleteDocument: (projectId: number, documentId: number) =>
    json<{ deleted: boolean }>(
      `/api/projects/${projectId}/documents/${documentId}`,
      { method: "DELETE" },
    ),
  tasks: (projectId: number) => json<unknown[]>(`/api/projects/${projectId}/tasks`),
  workflowRuns: (projectId?: number) => {
    const q = projectId != null ? `?project_id=${projectId}` : "";
    return json<unknown[]>(`/api/workflows/runs${q}`);
  },
  startWorkflow: (body: {
    agent_id: number;
    project_id: number;
    agent_provider?: string;
    execute_mode?: string;
    concurrent_tasks?: boolean;
    batch_tasks?: boolean;
    require_human_review?: boolean;
  }) =>
    json<{ workflow_id: string }>("/api/workflows/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  temporalExecutions: (pageSize = 50) =>
    json<TemporalExecutionRow[]>(`/api/temporal/executions?page_size=${pageSize}`),
  temporalSnapshot: (workflowId: string, runId?: string | null) => {
    const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
    return json<TemporalSnapshot>(
      `/api/temporal/executions/${encodeURIComponent(workflowId)}/snapshot${q}`,
    );
  },
  temporalTargetFromWorkflowRun: (workflowRunId: number) =>
    json<TemporalTarget>(`/api/temporal/workflow-runs/${workflowRunId}/target`),
};
