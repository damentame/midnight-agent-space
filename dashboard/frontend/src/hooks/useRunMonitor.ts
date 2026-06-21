import { useCallback, useEffect, useState } from "react";
import {
  api,
  sseRunEventsUrl,
  type AgentArtifact,
  type AgentEvent,
  type AgentRun,
  type GitChange,
  type ProjectDocument,
} from "../api";

export type RunMonitorState = {
  run: AgentRun | null;
  events: AgentEvent[];
  artifacts: AgentArtifact[];
  changes: GitChange[];
  tasks: Record<string, unknown>[];
  documents: ProjectDocument[];
  sseStatus: "idle" | "connecting" | "live" | "closed" | "error";
  err: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
};

export function useRunMonitor(projectId: number, runId: number): RunMonitorState {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [artifacts, setArtifacts] = useState<AgentArtifact[]>([]);
  const [changes, setChanges] = useState<GitChange[]>([]);
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([]);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [sseStatus, setSseStatus] = useState<RunMonitorState["sseStatus"]>("idle");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!Number.isFinite(projectId) || !Number.isFinite(runId)) return;
    const [runRow, eventRows, artifactRows, changeRows, taskRows, documentRows] = await Promise.all([
      api.projectRun(projectId, runId),
      api.projectRunEvents(projectId, runId, 1000),
      api.projectRunArtifacts(projectId, runId, 300),
      api.projectRunChanges(projectId, runId, 1000),
      api.tasks(projectId),
      api.documents(projectId),
    ]);
    setRun(runRow);
    setEvents(eventRows);
    setArtifacts(artifactRows);
    setChanges(changeRows);
    setTasks(taskRows as Record<string, unknown>[]);
    setDocuments(documentRows);
    setErr(null);
  }, [projectId, runId]);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e) => setErr(String(e.message)))
      .finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !Number.isFinite(runId)) return;
    setSseStatus("connecting");
    const source = new EventSource(sseRunEventsUrl(projectId, runId));
    source.onopen = () => setSseStatus("live");
    source.onerror = () => {
      setSseStatus("error");
      setErr("Live event stream disconnected. Refreshing via polling.");
    };
    source.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data) as AgentEvent;
        setEvents((prev) => {
          if (prev.some((item) => item.agent_event_id === parsed.agent_event_id)) return prev;
          return [...prev, parsed];
        });
        const eventType = String(parsed.event_type ?? "");
        if (eventType.startsWith("TASK_") || eventType.startsWith("RUN_")) {
          refresh().catch((e) => setErr(String((e as Error).message ?? e)));
        }
      } catch {
        // ignore malformed SSE payloads
      }
    };
    return () => {
      source.close();
      setSseStatus("closed");
    };
  }, [projectId, runId, refresh]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !Number.isFinite(runId)) return;
    const interval = window.setInterval(() => {
      const currentStatus = String(run?.status ?? "").toUpperCase();
      if (!["COMPLETED", "FAILED", "CANCELLED", "BLOCKED"].includes(currentStatus)) {
        refresh().catch((e) => setErr(String((e as Error).message ?? e)));
      }
    }, 10_000);
    return () => window.clearInterval(interval);
  }, [projectId, runId, run?.status, refresh]);

  return {
    run,
    events,
    artifacts,
    changes,
    tasks,
    documents,
    sseStatus,
    err,
    loading,
    refresh,
  };
}
