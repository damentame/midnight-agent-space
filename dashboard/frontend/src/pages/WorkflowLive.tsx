import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import type { TemporalActivity, TemporalSnapshot } from "../api";
import { api, wsTemporalExecutionUrl } from "../api";
import ActivityDots from "../components/ActivityDots";

export default function WorkflowLive() {
  const { workflowId: workflowIdParam } = useParams();
  const [search] = useSearchParams();
  const runId = search.get("run_id");

  const [manualId, setManualId] = useState(workflowIdParam ?? "");
  const workflowId = (workflowIdParam ?? manualId).trim();

  const [snapshot, setSnapshot] = useState<TemporalSnapshot | null>(null);
  const [wsStatus, setWsStatus] = useState<"idle" | "connecting" | "live" | "error">("idle");
  const [wsError, setWsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TemporalActivity | null>(null);

  const activities = snapshot?.activities ?? [];

  useEffect(() => {
    if (workflowIdParam) setManualId(workflowIdParam);
  }, [workflowIdParam]);

  useEffect(() => {
    if (!workflowId) return;
    api
      .temporalSnapshot(workflowId, runId)
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, [workflowId, runId]);

  useEffect(() => {
    if (!workflowId) return;
    let ws: WebSocket | null = null;
    setWsStatus("connecting");
    setWsError(null);
    try {
      ws = new WebSocket(wsTemporalExecutionUrl(workflowId, runId));
      ws.onopen = () => setWsStatus("live");
      ws.onmessage = (ev) => {
        try {
          const raw = JSON.parse(ev.data as string) as Record<string, unknown>;
          if (raw.type === "error") {
            setWsError(String(raw.message ?? "error"));
            return;
          }
          if (raw.type === "snapshot" && Array.isArray(raw.activities)) {
            setSnapshot({
              workflow_id: String(raw.workflow_id ?? ""),
              run_id: String(raw.run_id ?? ""),
              workflow_type: String(raw.workflow_type ?? ""),
              status: String(raw.status ?? ""),
              task_queue: raw.task_queue != null ? String(raw.task_queue) : undefined,
              history_event_count: Number(raw.history_event_count ?? 0),
              activities: raw.activities as TemporalActivity[],
            });
          }
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => setWsError("WebSocket error");
      ws.onclose = () => setWsStatus("idle");
    } catch (e) {
      setWsStatus("error");
      setWsError(String(e));
    }
    return () => {
      ws?.close();
    };
  }, [workflowId, runId]);

  const selectedId = selected?.scheduled_event_id ?? null;

  const meta = useMemo(
    () =>
      snapshot
        ? `${snapshot.workflow_type} · ${snapshot.status} · ${snapshot.history_event_count} history events`
        : "",
    [snapshot],
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <p className="heading-sub mb-1">Temporal</p>
          <h1 className="heading-main text-xl sm:text-2xl">Live workflow</h1>
          <p className="text-neutral-600 text-sm mt-2 max-w-xl">
            WebSocket snapshots every 2s from Temporal history. Dots = activity tasks; orange = running.
          </p>
        </div>
        <Link
          to="/workflows"
          className="text-sm text-orange-600 hover:text-orange-500 font-bold uppercase tracking-widest"
        >
          ← All workflows
        </Link>
      </div>

      {!workflowIdParam && (
        <div className="glass p-4 flex flex-wrap gap-2 items-end">
          <label className="block">
            <span className="heading-sub">Temporal workflow id</span>
            <input
              className="mt-1 block w-full min-w-[280px] bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
              placeholder="e.g. document-serialization-2-2"
              value={manualId}
              onChange={(e) => setManualId(e.target.value)}
            />
          </label>
          <Link
            to={`/workflows/live/${encodeURIComponent(manualId.trim())}`}
            className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold uppercase tracking-widest"
          >
            Connect
          </Link>
        </div>
      )}

      {workflowId && (
        <>
          <div className="glass p-4 space-y-1">
            <p className="font-mono text-sm text-neutral-800 break-all">{workflowId}</p>
            {runId && (
              <p className="font-mono text-xs text-neutral-600 break-all">run_id: {runId}</p>
            )}
            <p className="text-xs text-neutral-600">
              WS: {wsStatus}
              {wsError && <span className="text-neutral-700 ml-2">{wsError}</span>}
            </p>
            {meta && <p className="text-xs text-neutral-600">{meta}</p>}
          </div>

          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              {activities.length === 0 ? (
                <div className="glass p-8 text-center text-neutral-600 text-sm">
                  No activities yet (workflow missing or still starting).
                </div>
              ) : (
                <ActivityDots
                  activities={activities}
                  selectedId={selectedId}
                  onSelect={(a) => setSelected(a)}
                />
              )}
            </div>
            <div className="glass p-4 min-h-[200px]">
              <p className="heading-sub mb-3">Activity detail</p>
              {!selected ? (
                <p className="text-sm text-neutral-600">Select a dot or row.</p>
              ) : (
                <div className="space-y-3 text-sm">
                  <div>
                    <p className="heading-sub text-[10px]">Name</p>
                    <p className="text-neutral-900 font-medium">{selected.activity_name}</p>
                  </div>
                  <div>
                    <p className="heading-sub text-[10px]">Status</p>
                    <p className="text-neutral-700">{selected.status}</p>
                  </div>
                  <div>
                    <p className="heading-sub text-[10px]">Input</p>
                    <pre className="text-xs text-neutral-600 whitespace-pre-wrap break-words max-h-40 overflow-y-auto bg-paper-field p-2 rounded border border-neutral-300/80">
                      {selected.input_summary || "—"}
                    </pre>
                  </div>
                  <div>
                    <p className="heading-sub text-[10px]">Output</p>
                    <pre className="text-xs text-neutral-600 whitespace-pre-wrap break-words max-h-40 overflow-y-auto bg-paper-field p-2 rounded border border-neutral-300/80">
                      {selected.output_summary || "—"}
                    </pre>
                  </div>
                  {selected.error && (
                    <div>
                      <p className="heading-sub text-[10px]">Error</p>
                      <pre className="text-xs text-neutral-800 whitespace-pre-wrap break-words">{selected.error}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <button
            type="button"
            className="text-xs text-neutral-600 underline"
            onClick={() => {
              if (!workflowId) return;
              api.temporalSnapshot(workflowId, runId).then(setSnapshot).catch(() => {});
            }}
          >
            Refresh snapshot (REST)
          </button>
        </>
      )}
    </div>
  );
}
