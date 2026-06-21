import type { AgentEvent, AgentRun, ProjectDocument } from "../api";

export type TaskStatusKind = "pending" | "queued" | "running" | "completed" | "failed" | "cancelled" | "unknown";

export type TaskTimelineEntry = {
  task: Record<string, unknown>;
  taskId: number;
  key: string;
  name: string;
  status: string;
  statusKind: TaskStatusKind;
  progress: number;
  agent: string;
  depth: number;
  sequenceIndex: number;
  references: ProjectDocument[];
  referenceSnippet: string;
  elapsed: string;
  startMs: number | null;
  endMs: number | null;
  lastEventMs: number | null;
  isActive: boolean;
  isStalled: boolean;
  issueMessage: string | null;
  isParallel: boolean;
  batchLabel: string | null;
};

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function textValue(value: unknown, fallback = "-"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

/** API timestamps are UTC but often omit a Z suffix. */
export function parseApiTimestamp(value?: string | null): number | null {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const hasZone = /[zZ]$/.test(raw) || /[+-]\d{2}:\d{2}$/.test(raw);
  const normalized = hasZone ? raw : `${raw}Z`;
  const parsed = new Date(normalized).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

export function timestamp(value?: string | null): number | null {
  return parseApiTimestamp(value);
}

export function durationLabelMs(startMs?: number | null, endMs?: number | null): string {
  if (!startMs) return "not started";
  const end = endMs ?? Date.now();
  const seconds = Math.max(0, Math.floor((end - startMs) / 1000));
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

export function durationLabel(start?: string | null, end?: string | null): string {
  return durationLabelMs(timestamp(start), timestamp(end));
}

const RUN_EXECUTION_STATUSES = new Set(["RUNNING", "COMPLETED", "FAILED", "CANCELLED", "BLOCKED"]);

/** When this run instance actually started executing (not task board creation time). */
export function runExecutionStartMs(run: AgentRun | null, events: AgentEvent[] = []): number | null {
  const startedEvents = events
    .filter((event) => String(event.event_type ?? "").toUpperCase() === "RUN_STARTED")
    .map((event) => timestamp(event.created_at))
    .filter((value): value is number => value != null);
  if (startedEvents.length > 0) {
    return Math.min(...startedEvents);
  }

  const status = String(run?.status ?? "").toUpperCase();
  if (RUN_EXECUTION_STATUSES.has(status)) {
    return (
      timestamp(run?.started_at) ??
      timestamp(run?.updated_at) ??
      timestamp(run?.created_at)
    );
  }
  return null;
}

export function runExecutionEndMs(run: AgentRun | null, events: AgentEvent[] = []): number | null {
  const terminal = new Set(["RUN_COMPLETED", "RUN_FAILED", "RUN_CANCELLED"]);
  const fromEvents = events
    .filter((event) => terminal.has(String(event.event_type ?? "").toUpperCase()))
    .map((event) => timestamp(event.created_at))
    .filter((value): value is number => value != null);
  if (fromEvents.length > 0) {
    return Math.max(...fromEvents);
  }
  const status = String(run?.status ?? "").toUpperCase();
  if (["COMPLETED", "FAILED", "CANCELLED", "BLOCKED"].includes(status)) {
    return timestamp(run?.finished_at) ?? timestamp(run?.updated_at);
  }
  return null;
}

export function eventMessage(event: AgentEvent): string {
  const payload = asRecord(event.event_payload);
  const type = String(event.event_type ?? "").toUpperCase();
  if (type === "RATE_LIMIT_EVENT") {
    const info = asRecord(asRecord(payload.payload).rate_limit_info);
    const status = textValue(info.status, "unknown");
    const limitType = textValue(info.rateLimitType, "rate limit");
    return `Claude ${limitType} rate limit: ${status}`;
  }
  return textValue(payload.message ?? payload.summary ?? payload.command ?? payload.error, event.event_type);
}

const ACTIVE_STATUSES = new Set(["RUNNING", "STARTED", "IN_PROGRESS", "PROCESSING"]);
const COMPLETED_STATUSES = new Set(["COMPLETED", "DONE", "PASSED"]);
const FAILED_STATUSES = new Set(["FAILED", "ERROR", "CANCELLED", "BLOCKED"]);
const PENDING_STATUSES = new Set(["READY_FOR_AGENT", "PENDING", "PLANNED"]);
const QUEUED_STATUSES = new Set(["QUEUED"]);

export function classifyTaskStatus(status: string): TaskStatusKind {
  const value = status.toUpperCase();
  if (COMPLETED_STATUSES.has(value)) return "completed";
  if (FAILED_STATUSES.has(value)) return "failed";
  if (ACTIVE_STATUSES.has(value)) return "running";
  if (QUEUED_STATUSES.has(value)) return "queued";
  if (PENDING_STATUSES.has(value)) return "pending";
  if (value === "CANCELLED") return "cancelled";
  return "unknown";
}

export function completionFromStatus(taskStatus: string, runStatus?: string): number {
  const kind = classifyTaskStatus(taskStatus);
  if (kind === "completed") return 100;
  if (kind === "running") return 55;
  if (kind === "failed" || kind === "cancelled") return 85;
  if (kind === "queued") return 12;
  if (kind === "pending") return 0;
  return String(runStatus ?? "").toUpperCase() === "COMPLETED" ? 100 : 10;
}

export function taskTimingFromEvents(
  taskId: number,
  events: AgentEvent[],
  task: Record<string, unknown>,
  run: AgentRun | null,
): { startMs: number | null; endMs: number | null } {
  const relevant = events
    .filter((event) => Number(asRecord(event.event_payload).task_id) === taskId)
    .sort((a, b) => (timestamp(a.created_at) ?? 0) - (timestamp(b.created_at) ?? 0));

  let startMs: number | null = null;
  let endMs: number | null = null;

  for (const event of relevant) {
    const type = String(event.event_type ?? "").toUpperCase();
    const at = timestamp(event.created_at);
    if (!at) continue;
    if (["TASK_STARTED", "TASK_MODEL_SELECTED", "TASK_RUNNING"].includes(type)) {
      startMs = startMs ?? at;
    }
    if (type === "TASK_QUEUED" && !startMs) {
      startMs = at;
    }
    if (["TASK_COMPLETED", "TASK_FAILED", "TASK_CANCELLED"].includes(type)) {
      endMs = at;
      startMs = startMs ?? at;
    }
  }

  if (!startMs) {
    startMs =
      runExecutionStartMs(run, events) ??
      timestamp(run?.started_at ?? run?.created_at);
  }
  if (!endMs && ["COMPLETED", "DONE", "PASSED", "FAILED", "ERROR", "CANCELLED"].includes(textValue(task.status, "").toUpperCase())) {
    endMs = timestamp(textValue(task.updated_at, "")) ?? timestamp(run?.finished_at ?? run?.updated_at);
  }

  return { startMs, endMs };
}

export function lastEventMsForTask(taskId: number, events: AgentEvent[]): number | null {
  const relevant = eventsForTask(taskId, events);
  if (relevant.length === 0) return null;
  const times = relevant
    .map((event) => timestamp(event.created_at))
    .filter((value): value is number => value != null);
  return times.length > 0 ? Math.max(...times) : null;
}

export function issueMessageForTask(taskId: number, events: AgentEvent[]): string | null {
  const relevant = eventsForTask(taskId, events);
  for (let index = relevant.length - 1; index >= 0; index -= 1) {
    const event = relevant[index];
    const type = String(event.event_type ?? "").toUpperCase();
    const payload = asRecord(event.event_payload);
    if (type === "TASK_FAILED" || type === "PROCESS_EXIT") {
      const err = textValue(payload.error ?? payload.message, "");
      const exitCode = payload.exit_code;
      if (err) return err;
      if (exitCode != null && Number(exitCode) !== 0) {
        return `Process exited with code ${exitCode}`;
      }
    }
    if (type === "TIMEOUT") {
      return textValue(payload.message, "Task timed out");
    }
  }
  return null;
}

export function referencesForTask(task: Record<string, unknown>, documents: ProjectDocument[]): ProjectDocument[] {
  if (documents.length <= 2) return documents;
  const taskText = `${textValue(task.task_name)} ${textValue(task.description)} ${textValue(task.task_type)}`.toLowerCase();
  const preferredKinds = taskText.includes("review")
    ? ["fig", "image", ".png", ".jpg", ".pdf", ".docx", ".md"]
    : taskText.includes("implement")
      ? [".md", ".txt", ".json", ".tsx", ".ts", ".py", ".go"]
      : [".md", ".txt", ".json", ".pdf", ".docx"];
  return [...documents]
    .sort((a, b) => {
      const score = (doc: ProjectDocument) => {
        const ext = textValue(doc.file_extension, "").toLowerCase();
        const extScore = preferredKinds.findIndex((item) => ext.includes(item));
        const name = textValue(doc.document_name, "").toLowerCase();
        const nameScore = name && taskText.includes(name.replace(/\.[^.]+$/, "")) ? 3 : 0;
        return (extScore === -1 ? 0 : preferredKinds.length - extScore) + nameScore;
      };
      return score(b) - score(a);
    })
    .slice(0, 2);
}

export function taskStatusFromRunEvents(
  taskId: number,
  events: AgentEvent[],
  fallbackStatus: string,
): string {
  const relevant = eventsForTask(taskId, events);
  if (relevant.length === 0) {
    return fallbackStatus;
  }
  let status = fallbackStatus.toUpperCase();
  for (const event of relevant) {
    const type = String(event.event_type ?? "").toUpperCase();
    if (type === "TASK_QUEUED") status = "QUEUED";
    if (type === "TASK_MODEL_SELECTED" || type === "TASK_STARTED" || type === "TASK_RUNNING") status = "RUNNING";
    if (type === "TASK_COMPLETED") status = "COMPLETED";
    if (type === "TASK_FAILED") status = "FAILED";
    if (type === "TASK_CANCELLED") status = "CANCELLED";
  }
  return status;
}

export function buildTaskTimelineEntries(
  tasks: Record<string, unknown>[],
  events: AgentEvent[],
  run: AgentRun | null,
  documents: ProjectDocument[],
): TaskTimelineEntry[] {
  const runStatus = String(run?.status ?? "").toUpperCase();
  const runtimeProvider = run?.runtime_provider;

  return tasks.map((task, index) => {
    const taskId = Number(task.task_id);
    const dbStatus = textValue(task.status, "PENDING").toUpperCase();
    const taskStatus = Number.isFinite(taskId)
      ? taskStatusFromRunEvents(taskId, events, dbStatus)
      : dbStatus;
    const statusKind = classifyTaskStatus(taskStatus);
    const taskData = asRecord(task.task_data);
    const sequenceIndex = Number(taskData.sequence_index ?? taskData.order ?? index);
    const depth = Number(taskData.depth ?? taskData.tree_depth ?? 0);
    const { startMs, endMs } = Number.isFinite(taskId)
      ? taskTimingFromEvents(taskId, events, task, run)
      : { startMs: null, endMs: null };
    const lastEventMs = Number.isFinite(taskId) ? lastEventMsForTask(taskId, events) : null;
    const issueMessage = Number.isFinite(taskId) ? issueMessageForTask(taskId, events) : null;
    const stallThresholdMs = 10 * 60 * 1000;

    const explicitAgent = textValue(asRecord(task.parameters).assigned_agent ?? taskData.assigned_agent, "");
    const agent =
      explicitAgent ||
      (runtimeProvider === "claude-cli"
        ? "Claude CLI"
        : runtimeProvider === "codex-cli"
          ? "Codex CLI"
          : textValue(runtimeProvider, "Agent executor"));

    const references = referencesForTask(task, documents);
    const referenceSnippet =
      textValue(references[0]?.raw_text_preview, "") ||
      `${textValue(references[0]?.document_name, "Project context")} is included in this workload.`;
    const isParallel =
      textValue(taskData.execution_mode, "").toLowerCase() === "parallel" ||
      textValue(taskData.parallel_group, "") === "sections";
    const batchLabel = textValue(taskData.execution_batch_label, "") || null;

    return {
      task,
      taskId: Number.isFinite(taskId) ? taskId : index,
      key: String(Number.isFinite(taskId) ? taskId : index),
      name: textValue(task.task_name ?? task.title, `Task ${index + 1}`),
      status: taskStatus,
      statusKind,
      progress: completionFromStatus(taskStatus, runStatus),
      agent,
      depth: Number.isFinite(depth) ? depth : 0,
      sequenceIndex: Number.isFinite(sequenceIndex) ? sequenceIndex : index,
      references,
      referenceSnippet,
      elapsed: durationLabelMs(
        startMs,
        endMs ??
          (COMPLETED_STATUSES.has(taskStatus) || FAILED_STATUSES.has(taskStatus)
            ? timestamp(textValue(task.updated_at, "")) ?? runExecutionEndMs(run, events)
            : null),
      ),
      startMs,
      endMs,
      lastEventMs,
      isActive:
        (statusKind === "running" || ACTIVE_STATUSES.has(taskStatus)) &&
        !["COMPLETED", "FAILED", "CANCELLED", "BLOCKED"].includes(String(run?.status ?? "").toUpperCase()) &&
        statusKind !== "failed",
      isStalled:
        (statusKind === "running" || ACTIVE_STATUSES.has(taskStatus)) &&
        lastEventMs != null &&
        Date.now() - lastEventMs > stallThresholdMs,
      issueMessage,
      isParallel,
      batchLabel,
    };
  });
}

export function eventsForTask(taskId: number, events: AgentEvent[]): AgentEvent[] {
  return events
    .filter((event) => Number(asRecord(event.event_payload).task_id) === taskId)
    .sort((a, b) => (timestamp(a.created_at) ?? 0) - (timestamp(b.created_at) ?? 0));
}

export function timelineWindow(
  entries: TaskTimelineEntry[],
  run: AgentRun | null,
  nowMs = Date.now(),
  events: AgentEvent[] = [],
): { originMs: number; endMs: number; spanMs: number; nowPercent: number } {
  const runStart = runExecutionStartMs(run, events) ?? nowMs;
  const runTerminal = ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED"].includes(
    String(run?.status ?? "").toUpperCase(),
  );
  const runEnd = runExecutionEndMs(run, events);
  const candidates = [runStart];
  for (const entry of entries) {
    if (entry.startMs) candidates.push(entry.startMs);
    if (entry.endMs) candidates.push(entry.endMs);
    if (entry.isActive) candidates.push(nowMs);
  }
  const originMs = Math.min(...candidates);
  const endMs = runTerminal
    ? Math.max(runEnd ?? nowMs, ...candidates)
    : Math.max(nowMs, ...candidates.filter((value) => value <= nowMs + 1000));
  const spanMs = Math.max(endMs - originMs, 60_000);
  const nowPercent = runTerminal ? 100 : Math.min(100, Math.max(0, ((nowMs - originMs) / spanMs) * 100));
  return { originMs, endMs, spanMs, nowPercent };
}

export function formatTimelineTick(ms: number, originMs: number): string {
  const deltaSec = Math.max(0, Math.floor((ms - originMs) / 1000));
  if (deltaSec < 60) return `${deltaSec}s`;
  const minutes = Math.floor(deltaSec / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h`;
}

const TERMINAL_RUN_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED", "BLOCKED"]);
const ACTIVE_RUN_STATUSES = new Set(["RUNNING", "PENDING", "STARTED"]);

/** Pick the run that should drive the execute board (avoid pinning stale failed runs). */
export function resolveBoardRun(runs: AgentRun[], tasksAwaitingRun: boolean): AgentRun | undefined {
  const latestRun = runs[0];
  const activeRun = runs.find((run) => ACTIVE_RUN_STATUSES.has(String(run.status ?? "").toUpperCase()));
  const latestRunIsTerminal =
    Boolean(latestRun) && TERMINAL_RUN_STATUSES.has(String(latestRun?.status ?? "").toUpperCase());
  return activeRun ?? (latestRunIsTerminal && tasksAwaitingRun ? undefined : latestRun);
}
