import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  sseRunEventsUrl,
  type AgentArtifact,
  type AgentEvent,
  type AgentRun,
  type GitChange,
} from "../api";

export default function RunDetail() {
  const { id, runId } = useParams();
  const projectId = Number(id);
  const runIdNum = Number(runId);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [artifacts, setArtifacts] = useState<AgentArtifact[]>([]);
  const [changes, setChanges] = useState<GitChange[]>([]);
  const [sseStatus, setSseStatus] = useState<"idle" | "connecting" | "live" | "closed" | "error">("idle");
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    if (!Number.isFinite(projectId) || !Number.isFinite(runIdNum)) return;
    const [runRow, eventRows, artifactRows, changeRows] = await Promise.all([
      api.projectRun(projectId, runIdNum),
      api.projectRunEvents(projectId, runIdNum, 1000),
      api.projectRunArtifacts(projectId, runIdNum, 300),
      api.projectRunChanges(projectId, runIdNum, 1000),
    ]);
    setRun(runRow);
    setEvents(eventRows);
    setArtifacts(artifactRows);
    setChanges(changeRows);
  };

  useEffect(() => {
    load().catch((e) => setErr(String(e.message)));
  }, [projectId, runIdNum]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !Number.isFinite(runIdNum)) return;
    setSseStatus("connecting");
    const source = new EventSource(sseRunEventsUrl(projectId, runIdNum));
    source.onopen = () => setSseStatus("live");
    source.onerror = () => setSseStatus("error");
    source.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data) as AgentEvent;
        setEvents((prev) => {
          if (prev.some((item) => item.agent_event_id === parsed.agent_event_id)) return prev;
          return [...prev, parsed];
        });
      } catch {
        // Keep SSE resilient during transient malformed payloads.
      }
    };
    return () => {
      source.close();
      setSseStatus("closed");
    };
  }, [projectId, runIdNum]);

  const review = useMemo(
    () => (run?.result_payload as Record<string, unknown> | undefined)?.review as
      | { ok?: boolean; checks?: { check: string; ok: boolean; value: unknown }[] }
      | undefined,
    [run],
  );

  if (!Number.isFinite(projectId) || !Number.isFinite(runIdNum)) {
    return <p className="text-sm text-neutral-600">Invalid project/run identifier.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Link to={`/projects/${projectId}`} className="text-xs font-bold uppercase tracking-widest text-orange-600">
          ← Project
        </Link>
        <span className="text-xs text-neutral-600 uppercase tracking-wide">SSE: {sseStatus}</span>
      </div>

      {err && <div className="text-sm text-neutral-700">{err}</div>}

      <div className="glass p-5 border-neutral-200 space-y-2">
        <h1 className="heading-main text-lg">Run #{runIdNum}</h1>
        <p className="text-xs text-neutral-600">
          Status: <span className="font-bold">{run?.status ?? "loading"}</span> · Provider:{" "}
          <span className="font-bold">{run?.runtime_provider ?? "—"}</span>
        </p>
        <p className="text-xs text-neutral-600 break-all">Command: {run?.command_preview || "—"}</p>
        <div className="flex gap-2">
          <button
            type="button"
            className="px-3 py-1 rounded border border-neutral-400 text-[10px] font-bold uppercase tracking-widest text-neutral-600"
            onClick={async () => {
              await api.cancelProjectRun(projectId, runIdNum);
              await load();
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            className="px-3 py-1 rounded border border-neutral-400 text-[10px] font-bold uppercase tracking-widest text-neutral-600"
            onClick={async () => {
              await api.retryProjectRun(projectId, runIdNum);
              await load();
            }}
          >
            Retry
          </button>
          <button
            type="button"
            className="px-3 py-1 rounded border border-orange-600 text-[10px] font-bold uppercase tracking-widest text-orange-600"
            onClick={() => load().catch(() => {})}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="glass p-4 border-neutral-200">
          <h2 className="heading-sub mb-3">Events</h2>
          <div className="max-h-[420px] overflow-y-auto divide-y divide-neutral-200">
            {events.map((event) => (
              <div key={event.agent_event_id} className="py-2 text-xs">
                <p className="text-neutral-800 font-medium">
                  {event.agent_event_id} · {event.event_type}
                </p>
                <pre className="text-neutral-600 whitespace-pre-wrap break-words mt-1">
                  {JSON.stringify(event.event_payload ?? {}, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="glass p-4 border-neutral-200">
            <h2 className="heading-sub mb-3">Artifacts</h2>
            <ul className="space-y-2 text-xs">
              {artifacts.map((artifact) => (
                <li key={artifact.agent_artifact_id} className="border border-neutral-300 rounded-lg p-2">
                  <p className="text-neutral-800">{artifact.artifact_name || "artifact"}</p>
                  <p className="text-neutral-600">
                    {artifact.artifact_type} · {artifact.size_bytes ?? 0} bytes
                  </p>
                  <p className="text-neutral-600 break-all">{artifact.artifact_path}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="glass p-4 border-neutral-200">
            <h2 className="heading-sub mb-3">Changed files</h2>
            <ul className="space-y-2 text-xs max-h-[220px] overflow-y-auto">
              {changes.map((change) => (
                <li key={change.git_change_id} className="border border-neutral-300 rounded-lg p-2">
                  <p className="text-neutral-800">
                    {change.change_type || "M"} · {change.file_path || "(summary)"}
                  </p>
                  {change.branch_name && (
                    <p className="text-neutral-600">
                      {change.branch_name} ← {change.base_branch}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="glass p-4 border-neutral-200">
        <h2 className="heading-sub mb-3">Verification</h2>
        {!review ? (
          <p className="text-xs text-neutral-600">No review payload recorded yet.</p>
        ) : (
          <ul className="space-y-2 text-xs">
            {(review.checks ?? []).map((check) => (
              <li key={check.check} className="border border-neutral-300 rounded-lg p-2 flex justify-between gap-3">
                <span className="text-neutral-800">{check.check}</span>
                <span className={check.ok ? "text-orange-700" : "text-neutral-700"}>
                  {String(check.value)} · {check.ok ? "ok" : "fail"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
