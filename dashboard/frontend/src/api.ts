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

function toQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
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

export type ProjectSummary = {
  project: Project;
  counts: {
    documents: number;
    tasks: number;
    runs: number;
  };
  latest_run: {
    agent_run_id: number;
    status: string;
    runtime_provider: string;
    created_at?: string | null;
    updated_at?: string | null;
  } | null;
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

export type ProjectDocument = {
  document_id: number;
  project_id: number;
  document_name: string;
  document_type: string | null;
  raw_text_content?: string | null;
  raw_text_preview?: string | null;
  file_extension?: string | null;
  file_mime_type?: string | null;
  file_size_bytes?: number | null;
  serialization_status?: string | null;
  version_number?: number | null;
  is_active_version?: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DocumentVersion = {
  document_version_id: number;
  project_id: number;
  document_id: number;
  version_number: number;
  version_label?: string | null;
  source?: string | null;
  content_hash?: string | null;
  change_summary?: string | null;
  raw_text_content?: string | null;
  structured_json?: Record<string, unknown> | null;
  created_by?: string | null;
  created_at?: string | null;
};

export type ProjectMetadata = {
  project_id: number;
  metadata: Record<string, unknown>;
  repository_url: string | null;
  default_branch: string | null;
  runtime_preferences: Record<string, unknown>;
  schema_ready: boolean;
};

export type AgentRun = {
  agent_run_id: number;
  project_id: number | null;
  runtime_provider: string | null;
  status: string | null;
  run_kind: string | null;
  request_payload?: Record<string, unknown> | null;
  context_pack?: Record<string, unknown> | null;
  command_preview?: string | null;
  result_payload?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type AgentEvent = {
  agent_event_id: number;
  agent_run_id: number;
  project_id?: number | null;
  event_type: string;
  event_order?: number | null;
  event_payload?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type AgentArtifact = {
  agent_artifact_id: number;
  agent_run_id: number;
  project_id?: number | null;
  artifact_type: string | null;
  artifact_name: string | null;
  artifact_path: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type GitChange = {
  git_change_id: number;
  agent_run_id?: number | null;
  project_id?: number | null;
  file_path?: string | null;
  change_type?: string | null;
  diff_excerpt?: string | null;
  branch_name?: string | null;
  base_branch?: string | null;
  commit_hash?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type QuickRunPlan = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  run: AgentRun;
  runtime: Record<string, unknown>;
  command: string[];
  worktree_plan: Record<string, unknown> | null;
  dry_run: boolean;
};

/** Browser WebSocket URL (via Vite proxy in dev). */
export function wsTemporalExecutionUrl(workflowId: string, runId?: string | null): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return `${proto}//${window.location.host}/ws/temporal/executions/${encodeURIComponent(workflowId)}${q}`;
}

export function sseRunEventsUrl(projectId: number, runId: number): string {
  return `/api/projects/${projectId}/runs/${runId}/events/stream`;
}

export const api = {
  stats: () => json<Stats>("/api/stats"),
  projects: (params?: { q?: string; status?: string; limit?: number; offset?: number }) =>
    json<Project[]>(`/api/projects${toQuery(params ?? {})}`),
  project: (id: number) => json<Project>(`/api/projects/${id}`),
  projectSummary: (id: number) => json<ProjectSummary>(`/api/projects/${id}/summary`),
  updateProject: (id: number, body: Partial<Project>) =>
    json<Project>(`/api/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  patchProject: (id: number, body: Partial<Project>) =>
    json<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  archiveProject: (id: number) =>
    json<Project>(`/api/projects/${id}/archive`, {
      method: "POST",
      body: JSON.stringify({}),
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
  documents: (projectId: number) => json<ProjectDocument[]>(`/api/projects/${projectId}/documents`),
  createDocument: (
    projectId: number,
    body: {
      document_name: string;
      document_type?: string;
      raw_text_content?: string;
      file_extension?: string;
      file_mime_type?: string;
    },
  ) =>
    json<ProjectDocument>(`/api/projects/${projectId}/documents`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  document: (projectId: number, documentId: number) =>
    json<ProjectDocument>(`/api/projects/${projectId}/documents/${documentId}`),
  patchDocument: (
    projectId: number,
    documentId: number,
    body: {
      document_name?: string;
      document_type?: string;
      raw_text_content?: string;
      serialization_status?: string;
      create_new_version?: boolean;
      version_label?: string;
      source?: string;
      change_summary?: string;
    },
  ) =>
    json<ProjectDocument>(`/api/projects/${projectId}/documents/${documentId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
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
  documentVersionsV2: (projectId: number, documentId: number, limit = 50) =>
    json<DocumentVersion[]>(
      `/api/projects/${projectId}/documents/${documentId}/versions?limit=${limit}`,
    ),
  documentVersionV2: (projectId: number, documentId: number, versionNumber: number) =>
    json<DocumentVersion>(
      `/api/projects/${projectId}/documents/${documentId}/versions/${versionNumber}`,
    ),
  createDocumentVersionV2: (
    projectId: number,
    documentId: number,
    body: {
      version_label?: string;
      source?: string;
      change_summary?: string;
      raw_text_content?: string;
      structured_json?: Record<string, unknown>;
      content_hash?: string;
      created_by?: string;
    },
  ) =>
    json<DocumentVersion>(`/api/projects/${projectId}/documents/${documentId}/versions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tasks: (projectId: number) => json<unknown[]>(`/api/projects/${projectId}/tasks`),
  projectRuns: (projectId: number, limit = 100) =>
    json<AgentRun[]>(`/api/projects/${projectId}/runs?limit=${limit}`),
  projectRun: (projectId: number, runId: number) =>
    json<AgentRun>(`/api/projects/${projectId}/runs/${runId}`),
  startProjectRun: (
    projectId: number,
    body: {
      user_prompt: string;
      template_name?: string;
      runtime_provider?: string;
      model?: string;
      include_change_history?: boolean;
      include_document_versions?: boolean;
      use_worktree?: boolean;
      execute?: boolean;
      dry_run?: boolean;
      created_by?: string;
      output_schema_name?: string;
    },
  ) =>
    json<QuickRunPlan>(`/api/projects/${projectId}/runs/start`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  quickRunForProject: (
    projectId: number,
    body: {
      user_prompt: string;
      template_name?: string;
      runtime_provider?: string;
      model?: string;
      include_change_history?: boolean;
      include_document_versions?: boolean;
      use_worktree?: boolean;
      execute?: boolean;
      dry_run?: boolean;
      created_by?: string;
      output_schema_name?: string;
    },
  ) =>
    json<QuickRunPlan>(`/api/projects/${projectId}/quick-runs`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cancelProjectRun: (projectId: number, runId: number) =>
    json<{ ok: boolean; status: string }>(`/api/projects/${projectId}/runs/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  retryProjectRun: (projectId: number, runId: number) =>
    json<QuickRunPlan>(`/api/projects/${projectId}/runs/${runId}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  projectRunEvents: (projectId: number, runId: number, limit = 500) =>
    json<AgentEvent[]>(`/api/projects/${projectId}/runs/${runId}/events?limit=${limit}`),
  projectRunArtifacts: (projectId: number, runId: number, limit = 200) =>
    json<AgentArtifact[]>(`/api/projects/${projectId}/runs/${runId}/artifacts?limit=${limit}`),
  projectRunChanges: (projectId: number, runId: number, limit = 500) =>
    json<GitChange[]>(`/api/projects/${projectId}/runs/${runId}/changes?limit=${limit}`),
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
  settingsRuntimes: () => json<Record<string, unknown>>("/api/settings/runtimes"),
  runtimeCheck: () => json<Record<string, unknown>>("/api/agentic/runtime/check"),
  projectMetadata: (projectId: number) =>
    json<ProjectMetadata>(`/api/agentic/projects/${projectId}/metadata`),
  updateProjectMetadata: (
    projectId: number,
    body: {
      metadata?: Record<string, unknown>;
      repository_url?: string;
      default_branch?: string;
      runtime_preferences?: Record<string, unknown>;
      updated_by?: string;
    },
  ) =>
    json<ProjectMetadata>(`/api/agentic/projects/${projectId}/metadata`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  documentVersions: (projectId: number, documentId: number, limit = 50) =>
    json<unknown[]>(
      `/api/agentic/projects/${projectId}/documents/${documentId}/versions?limit=${limit}`,
    ),
  createDocumentVersion: (
    projectId: number,
    documentId: number,
    body: {
      version_label?: string;
      source?: string;
      change_summary?: string;
      raw_text_content?: string;
      structured_json?: Record<string, unknown>;
      content_hash?: string;
      created_by?: string;
    },
  ) =>
    json<unknown>(`/api/agentic/projects/${projectId}/documents/${documentId}/versions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  changeHistory: (
    projectId: number,
    limit = 100,
    filters?: {
      entityType?: string;
      entityId?: number;
    },
  ) =>
    json<unknown[]>(
      `/api/projects/${projectId}/change-history${toQuery({
        limit,
        entityType: filters?.entityType,
        entityId: filters?.entityId,
      })}`,
    ),
  agentRuns: (projectId?: number, limit = 100) => {
    const q = projectId != null ? `?project_id=${projectId}&limit=${limit}` : `?limit=${limit}`;
    return json<AgentRun[]>(`/api/agentic/runs${q}`);
  },
  agentRun: (runId: number) => json<AgentRun>(`/api/agentic/runs/${runId}`),
  agentRunEvents: (runId: number, limit = 500) =>
    json<AgentEvent[]>(`/api/agentic/runs/${runId}/events?limit=${limit}`),
  agentRunArtifacts: (runId: number, limit = 200) =>
    json<AgentArtifact[]>(`/api/agentic/runs/${runId}/artifacts?limit=${limit}`),
  agentRunChanges: (runId: number, limit = 500) =>
    json<GitChange[]>(`/api/agentic/runs/${runId}/changes?limit=${limit}`),
  cancelAgentRun: (runId: number) =>
    json<{ ok: boolean; status: string }>(`/api/agentic/runs/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  retryAgentRun: (runId: number) =>
    json<QuickRunPlan>(`/api/agentic/runs/${runId}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  quickRun: (body: {
    project_id: number;
    user_prompt: string;
    template_name?: string;
    runtime_provider?: string;
    model?: string;
    include_change_history?: boolean;
    include_document_versions?: boolean;
    use_worktree?: boolean;
    dry_run?: boolean;
    created_by?: string;
    output_schema_name?: string;
  }) =>
    json<QuickRunPlan>("/api/agentic/quick-runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  promptTemplates: () =>
    json<{ templates: string[]; schemas: string[] }>("/api/agentic/prompt-templates"),
  promptTemplate: (templateName: string) =>
    json<{ template_name: string; content: string }>(
      `/api/agentic/prompt-templates/${encodeURIComponent(templateName)}`,
    ),
  jsonSchema: (schemaName: string) =>
    json<Record<string, unknown>>(`/api/agentic/json-schemas/${encodeURIComponent(schemaName)}`),
  parseCodexEvents: (lines: string[]) =>
    json<{ events: Record<string, unknown>[] }>("/api/agentic/codex/parse-events", {
      method: "POST",
      body: JSON.stringify({ lines }),
    }),
};
