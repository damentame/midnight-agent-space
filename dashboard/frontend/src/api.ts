const base = "";

export type CliRuntimeProvider = "codex-cli" | "claude-cli" | "cursor-agent";
export type ReviewerProvider = "codex-cli" | "claude-cli";

export type CliRuntimeStatus = {
  id: CliRuntimeProvider;
  label: string;
  found: boolean;
  configured_binary: string;
  default_model: string | null;
};

export type ModelCatalog = {
  selection_modes: { id: string; label: string; description: string }[];
  providers: Record<
    string,
    {
      label: string;
      optimized: { fast: string; complex: string; default: string };
      suggested_models: string[];
    }
  >;
  agent_effort_levels: string[];
};

export type FigmaSectionSummary = {
  slug?: string;
  name?: string;
  node_id?: string;
  node_count?: number;
  has_png?: boolean;
  section_export_document_id?: number;
};

export type FigmaImportResult = {
  ok: boolean;
  document_id: number;
  document_name: string;
  file_key: string;
  node_id?: string | null;
  image_document_ids: number[];
  section_export_document_ids?: number[];
  asset_document_ids?: number[];
  node_count?: number;
  preview?: string;
  warnings?: Array<string | { severity?: string; message?: string }>;
  extraction_version?: string;
  extraction_status?: string;
  sections?: FigmaSectionSummary[];
  assets?: Array<Record<string, unknown>>;
  tokens_summary?: { colors: number; typography: number; spacing: number };
};

export type DesignReadiness = {
  ok: boolean;
  required: boolean;
  structural_ready: boolean;
  gaps: string[];
  sections: FigmaSectionSummary[];
  assets: Array<Record<string, unknown>>;
  export_count: number;
  asset_count: number;
  extraction_version?: string;
  active_document_id?: number | null;
};

export type RuntimeCheck = {
  codex_cli: Record<string, unknown>;
  claude_cli: Record<string, unknown>;
  cli_runtimes?: CliRuntimeStatus[];
  cursor_agent?: Record<string, unknown>;
  reviewer_runtime?: { default?: string; options?: string[] };
  model_catalog?: ModelCatalog;
  git: Record<string, unknown>;
  workspace_root: string;
  midnight: Record<string, unknown>;
  hermes: Record<string, unknown>;
  environment: Record<string, unknown>;
};

export type AgentEffort = {
  level: string;
  score: number;
  rationale: string;
  execution_complexity?: string;
};

export type ApiErrorDetail = {
  detail: string;
  code?: string;
  hint?: string;
};

function parseApiErrorBody(raw: string, statusText: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return statusText;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; code?: string; hint?: string };
    const detail = parsed.detail;
    if (typeof detail === "string") {
      const parts = [detail];
      if (parsed.hint) parts.push(parsed.hint);
      return parts.join(" — ");
    }
    if (detail && typeof detail === "object" && !Array.isArray(detail) && "detail" in detail) {
      const structured = detail as ApiErrorDetail;
      const parts = [structured.detail];
      if (structured.hint) parts.push(structured.hint);
      return parts.join(" — ");
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item === "object" && item && "msg" in item ? String((item as { msg: unknown }).msg) : String(item)))
        .join("; ");
    }
  } catch {
    // not JSON
  }
  return trimmed;
}

const DEFAULT_FETCH_TIMEOUT_MS = 20_000;

async function json<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let r: Response;
  try {
    r = await fetch(`${base}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(
        `Request timed out (${path}). Check that the API is running on port 8001 and Postgres is reachable.`,
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
  if (!r.ok) {
    const t = await r.text();
    const message = parseApiErrorBody(t, r.statusText);
    if (r.status === 404) {
      throw new Error(
        `${message} (${path}). If you recently updated the dashboard, restart the API on port 8001.`,
      );
    }
    if (
      (r.status === 500 || r.status === 502 || r.status === 503) &&
      (!t.trim() || message.toLowerCase() === "internal server error")
    ) {
      throw new Error(
        `MAS API is not reachable (${path}). Start Docker Desktop, run "docker compose up -d postgres", then start the API on port 8001.`,
      );
    }
    throw new Error(message);
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
  content_kind?: string | null;
  content_summary?: string | null;
  user_instructions?: string | null;
  has_file_content?: boolean | null;
  serialization_status?: string | null;
  embedding_status?: string | null;
  version_number?: number | null;
  is_active_version?: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type UploadSettings = {
  max_size_bytes: number;
  max_size_mb: number;
  allowed_extensions: string[];
};

export type ProjectTask = {
  task_id: number;
  project_id: number;
  agent_id?: number | null;
  document_id?: number | null;
  task_name?: string | null;
  task_type?: string | null;
  description?: string | null;
  parameters?: Record<string, unknown> | null;
  status?: string | null;
  priority?: number | null;
  task_notes?: string | null;
  task_data?: Record<string, unknown> | null;
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

export type ProgressMilestone = {
  index: number;
  name: string;
  status: "pending" | "in_progress" | "completed" | string;
  task_count: number;
  completed_count: number;
  percent_target: number;
};

export type ProgressTaskSummary = {
  task_id?: number | null;
  task_name?: string | null;
  milestone_name?: string | null;
  status?: string | null;
};

export type ProjectProgress = {
  ok: boolean;
  project_id: number;
  percent_complete: number;
  total_tasks: number;
  completed_task_count: number;
  milestones: ProgressMilestone[];
  completed_tasks: ProgressTaskSummary[];
  in_progress_tasks: ProgressTaskSummary[];
  pending_tasks: ProgressTaskSummary[];
  risks: string[];
  generated_at: string;
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
  already_running?: boolean;
  message?: string;
  source_run_id?: number;
  continue_from_task?: {
    task_id: number;
    task_name?: string;
    task_index?: number | null;
    status?: string | null;
  };
};

export type LocalPathFolder = {
  name: string;
  path: string;
  is_git_repo: boolean;
};

export type LocalPathBrowse = {
  current_path: string;
  parent_path: string | null;
  home_path: string;
  drives: string[];
  is_git_repo: boolean;
  git_repos: LocalPathFolder[];
  folders: LocalPathFolder[];
};

export type WorkspacePrepareResult = {
  ok: boolean;
  repo_path?: string;
  created?: boolean;
  initialized?: boolean;
  folder_name?: string;
  parent_path?: string;
  message?: string;
  error?: string;
  project_id?: number;
  saved_to_project?: boolean;
};

export type CodebaseSerializeStatus = {
  status: string;
  phase: string;
  message: string;
  current: number;
  total: number;
  percent: number;
  files_seen?: number;
  files_imported?: number;
  files_skipped?: number;
  error?: string | null;
  long_running?: boolean;
  result?: {
    ok?: boolean;
    files_imported?: number;
    files_skipped?: number;
    files_discovered?: number;
    error?: string;
  } | null;
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
  browseLocalPaths: (path?: string) =>
    json<LocalPathBrowse>(`/api/local-paths/browse${toQuery({ path })}`),
  defaultWorkspaceParent: () =>
    json<{ parent_path: string; exists: boolean }>("/api/projects/workspace/default-parent"),
  prepareProjectWorkspace: (
    projectId: number,
    body: {
      mode: "create" | "init_here" | "use_existing";
      parent_path?: string;
      existing_path?: string;
      save_to_project?: boolean;
    },
  ) =>
    json<WorkspacePrepareResult>(`/api/projects/${projectId}/workspace/prepare`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  startCodebaseSerialize: (projectId: number, body?: { repo_path?: string; max_files?: number }) =>
    json<{ ok: boolean; status?: string; message?: string; error?: string }>(
      `/api/projects/${projectId}/codebase/serialize`,
      {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      },
    ),
  codebaseSerializeStatus: (projectId: number) =>
    json<CodebaseSerializeStatus>(`/api/projects/${projectId}/codebase/serialize/status`),
  projects: (params?: { q?: string; status?: string; limit?: number; offset?: number }) =>
    json<Project[]>(`/api/projects${toQuery(params ?? {})}`),
  project: (id: number) => json<Project>(`/api/projects/${id}`),
  projectSummary: (id: number) => json<ProjectSummary>(`/api/projects/${id}/summary`),
  batchProjectSummaries: (limit = 12) =>
    json<{ ok: boolean; summaries: ProjectSummary[] }>(`/api/projects/batch-summaries?limit=${limit}`),
  projectHealth: (id: number) =>
    json<{
      ok: boolean;
      project_id: number;
      latest_run?: Record<string, unknown> | null;
      preview?: Record<string, unknown>;
      runnable?: { ok: boolean; errors: string[]; warnings: string[] };
      runtime_preferences?: Record<string, unknown>;
    }>(`/api/projects/${id}/health`),
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
  validateFigmaToken: (token: string) =>
    json<{ ok: boolean; email?: string; handle?: string }>("/api/settings/figma/validate-token", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  importFigmaDesign: (
    projectId: number,
    body: { url: string; notes?: string; token?: string },
  ) =>
    json<FigmaImportResult>(`/api/projects/${projectId}/figma/import`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reimportFigmaDesign: (
    projectId: number,
    body: { url?: string; notes?: string; token?: string } = {},
  ) =>
    json<FigmaImportResult>(`/api/projects/${projectId}/figma/reimport`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  importDesignPack: async (projectId: number, file: File, notes?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (notes?.trim()) fd.append("notes", notes.trim());
    const r = await fetch(`/api/projects/${projectId}/design-pack/import`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) {
      const raw = await r.text();
      throw new Error(parseApiErrorBody(raw, r.statusText));
    }
    return r.json() as Promise<FigmaImportResult>;
  },
  getDesignReadiness: (projectId: number) =>
    json<DesignReadiness>(`/api/projects/${projectId}/design-readiness`),
  uploadSettings: () => json<UploadSettings>("/api/settings/uploads"),
  uploadDocument: async (projectId: number, file: File, instructions?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (instructions?.trim()) fd.append("instructions", instructions.trim());
    const r = await fetch(`/api/projects/${projectId}/documents/upload`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) {
      const raw = await r.text();
      let message = raw || r.statusText;
      try {
        const parsed = JSON.parse(raw) as { detail?: string };
        if (typeof parsed.detail === "string") message = parsed.detail;
      } catch {
        // use raw response text
      }
      throw new Error(message);
    }
    return r.json() as Promise<ProjectDocument>;
  },
  documentFileBlob: async (projectId: number, documentId: number) => {
    const r = await fetch(`/api/projects/${projectId}/documents/${documentId}/file`);
    if (!r.ok) throw new Error(await r.text());
    return r.blob();
  },
  deleteDocument: (projectId: number, documentId: number) =>
    json<{ deleted: boolean; document_id: number }>(
      `/api/projects/${projectId}/documents/${documentId}`,
      { method: "DELETE" },
    ),
  deleteDocuments: (projectId: number, documentIds: number[]) =>
    json<{ deleted: number; document_ids: number[] }>(
      `/api/projects/${projectId}/documents/batch-delete`,
      {
        method: "POST",
        body: JSON.stringify({ document_ids: documentIds }),
      },
    ),
  analyzeProject: (
    projectId: number,
    body: {
      goal: string;
      repo_path?: string;
      repository_url?: string;
      default_branch?: string;
      preview_command?: string;
      preview_url?: string;
      acceptance_criteria?: string[];
      team?: Record<string, unknown>[];
      execution_parameters?: Record<string, unknown>;
      manual_edit_instructions?: string;
    },
  ) =>
    json<Record<string, unknown>>(`/api/projects/${projectId}/analysis-plan`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  startProjectPreview: (projectId: number) =>
    json<{
      ok: boolean;
      preview_url?: string;
      open_url?: string;
      command?: string;
      error?: string;
      auto_detected?: boolean;
      phase?: string;
      reachable?: boolean;
      status_code?: number;
      message?: string;
      allocated_port?: number;
      port_note?: string;
      working_directory?: string;
      steps?: Array<{
        id: string;
        label: string;
        status: string;
        detail?: string;
      }>;
    }>(`/api/projects/${projectId}/preview`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  projectPreviewStatus: (projectId: number) =>
    json<{
      ok: boolean;
      phase?: string;
      reachable?: boolean;
      preview_url?: string | null;
      open_url?: string;
      final_url?: string;
      preview_command?: string | null;
      message?: string;
      status_code?: number;
      started_at?: string;
      error?: string;
    }>(`/api/projects/${projectId}/preview/status`),
  projectProgress: (projectId: number) =>
    json<ProjectProgress>(`/api/projects/${projectId}/progress`),
  promoteProjectToMain: (projectId: number) =>
    json<{ ok: boolean; from_branch?: string; to_branch?: string; commit_hash?: string; synced_worktree?: string | null }>(
      `/api/projects/${projectId}/promote-to-main`,
      { method: "POST", body: JSON.stringify({}) },
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
  tasks: (projectId: number) => json<ProjectTask[]>(`/api/projects/${projectId}/tasks`),
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
      model_selection_mode?: string;
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
      reviewer_provider?: string;
      model?: string;
      model_selection_mode?: string;
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
  cleanupProjectRun: (projectId: number, runId: number, body?: { delete_record?: boolean }) =>
    json<{
      ok: boolean;
      run_id: number;
      git?: Record<string, unknown>;
      deleted?: Record<string, number>;
      delete_record?: boolean;
    }>(`/api/projects/${projectId}/runs/${runId}/cleanup`, {
      method: "POST",
      body: JSON.stringify(body ?? { delete_record: true }),
    }),
  retryProjectRun: (projectId: number, runId: number) =>
    json<QuickRunPlan>(`/api/projects/${projectId}/runs/${runId}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  detectProjectPreview: (projectId: number) =>
    json<{
      ok: boolean;
      repo_path?: string;
      preview_command?: string;
      preview_url?: string;
      framework?: string;
      working_directory?: string;
      detected_from?: string;
      allocated_port?: number;
      port_note?: string;
      error?: string;
    }>(`/api/projects/${projectId}/preview/detect`),
  reconcileProjectRun: (projectId: number, runId: number) =>
    json<{
      ok: boolean;
      run_id: number;
      status?: string;
      reconciled_tasks?: Record<number, string>;
      already_terminal?: boolean;
      error?: string;
    }>(`/api/projects/${projectId}/runs/${runId}/reconcile`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  projectRunEvents: (projectId: number, runId: number, limit = 500, mode: "timeline" | "full" = "timeline") =>
    json<AgentEvent[]>(
      `/api/projects/${projectId}/runs/${runId}/events?limit=${limit}&mode=${mode}`,
    ),
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
  settingsRuntimes: () => json<RuntimeCheck>("/api/settings/runtimes"),
  modelSettings: () => json<ModelCatalog>("/api/settings/models"),
  runtimeCheck: () => json<RuntimeCheck>("/api/agentic/runtime/check"),
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
  projectVersionHistory: (projectId: number) =>
    json<{
      ok: boolean;
      project_id: number;
      version_history: Array<{
        version: number;
        git_tag?: string | null;
        commit_hash?: string | null;
        reason?: string;
        created_at?: string;
        runs_cleaned?: number;
        tasks_reset?: number;
      }>;
      refresh_events?: unknown[];
    }>(`/api/projects/${projectId}/version-history`),
  refreshProject: (
    projectId: number,
    body: { reason: string; created_by?: string },
  ) =>
    json<{
      ok: boolean;
      project_id: number;
      version: number;
      snapshot: Record<string, unknown>;
      runs_cleaned: number;
      tasks_reset: number;
      version_history_entry: Record<string, unknown>;
    }>(`/api/projects/${projectId}/refresh`, {
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
    model_selection_mode?: string;
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
