import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import RunTaskTimeline from "../components/run-monitor/RunTaskTimeline";
import StatusBanner from "../components/StatusBanner";
import TaskStatusBadge from "../components/run-monitor/TaskStatusBadge";
import { useRunMonitor } from "../hooks/useRunMonitor";
import { api } from "../api";
import {
  asRecord,
  buildTaskTimelineEntries,
  durationLabel,
  durationLabelMs,
  eventMessage,
  runExecutionEndMs,
  runExecutionStartMs,
  textValue,
  timestamp,
} from "../lib/runMonitor";

export default function RunDetail() {
  const { id, runId } = useParams();
  const navigate = useNavigate();
  const projectId = Number(id);
  const runIdNum = Number(runId);
  const [previewMsg, setPreviewMsg] = useState<string | null>(null);
  const [cleanupMsg, setCleanupMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const { run, events, artifacts, changes, tasks, documents, sseStatus, err, refresh } = useRunMonitor(
    projectId,
    runIdNum,
  );

  const review = useMemo(
    () =>
      (run?.result_payload as Record<string, unknown> | undefined)?.review as
        | { ok?: boolean; checks?: { check: string; ok: boolean; value: unknown }[] }
        | undefined,
    [run],
  );
  const resultPayload = asRecord(run?.result_payload);
  const featureReview = asRecord(asRecord(resultPayload.review).feature_review);
  const featureReviewRecord = asRecord(featureReview);
  const designFidelity = asRecord(resultPayload.design_fidelity ?? featureReviewRecord.design_fidelity);

  const status = String(run?.status ?? "loading").toUpperCase();
  const timelineEntries = useMemo(
    () => buildTaskTimelineEntries(tasks, events, run, documents),
    [tasks, events, run, documents],
  );
  const completedTasks = timelineEntries.filter((row) => row.progress >= 100);
  const failedTasks = timelineEntries.filter((row) => row.statusKind === "failed");
  const activeTaskRow =
    timelineEntries.find((row) => row.isActive) ??
    timelineEntries.find((row) => row.statusKind === "queued" || row.statusKind === "pending") ??
    timelineEntries[0];
  const completionPercent =
    timelineEntries.length > 0
      ? Math.round(timelineEntries.reduce((sum, row) => sum + row.progress, 0) / timelineEntries.length)
      : status === "COMPLETED"
        ? 100
        : 0;
  const runStartMs = runExecutionStartMs(run, events);
  const runEndMs = runExecutionEndMs(run, events);
  const start = run?.started_at ?? run?.created_at;
  const finish = run?.finished_at ?? run?.updated_at;
  const longRun =
    Boolean(runStartMs && !["COMPLETED", "FAILED", "CANCELLED"].includes(status)) &&
    Date.now() - runStartMs > 30 * 60 * 1000;
  const retryEvents = events.filter((event) => event.event_type.toLowerCase().includes("retry"));
  const errorEvents = events.filter(
    (event) => event.event_type.toLowerCase().includes("error") || event.event_type.toLowerCase().includes("failed"),
  );
  const commandEvents = events.filter((event) => event.event_type.toLowerCase().includes("command")).slice(-8);
  const recentEvents = events.slice(-10).reverse();
  const referencedDocuments = documents.slice(0, 6);
  const executionPayload = asRecord(resultPayload.execution);
  const resultWarnings = Array.isArray(resultPayload.warnings) ? resultPayload.warnings.map((item) => String(item)) : [];
  const resultErrors = Array.isArray(resultPayload.errors)
    ? resultPayload.errors.map((item) => String(item))
    : textValue(resultPayload.error, "")
      ? [textValue(resultPayload.error)]
      : [];
  const executionError = textValue(executionPayload.error, "");
  if (executionError && !resultErrors.includes(executionError)) {
    resultErrors.unshift(executionError);
  }
  const featureContextUsed = Array.isArray(featureReviewRecord.context_used)
    ? featureReviewRecord.context_used.map((item) => asRecord(item))
    : [];
  const featureDesignRefs = Array.isArray(featureReviewRecord.design_references_used)
    ? featureReviewRecord.design_references_used.map((item) => asRecord(item))
    : [];
  const featureDesignGaps = Array.isArray(featureReviewRecord.design_reference_gaps)
    ? featureReviewRecord.design_reference_gaps.map((item) => String(item))
    : [];
  const orderedTasks = useMemo(
    () =>
      [...tasks].sort(
        (a, b) =>
          Number(a.priority ?? 999999) - Number(b.priority ?? 999999) ||
          Number(a.task_id ?? 0) - Number(b.task_id ?? 0),
      ),
    [tasks],
  );
  const continueFromTask = useMemo(() => {
    const index = orderedTasks.findIndex((task) => {
      const taskStatus = String(task.status ?? "").toUpperCase();
      return !["COMPLETED", "DONE", "PASSED"].includes(taskStatus);
    });
    if (index < 0) return null;
    const task = orderedTasks[index];
    return { index: index + 1, name: textValue(task.task_name, `Task ${index + 1}`), status: task.status };
  }, [orderedTasks]);

  if (!Number.isFinite(projectId) || !Number.isFinite(runIdNum)) {
    return <p className="text-sm text-neutral-600">Invalid project/run identifier.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Link to={`/projects/${projectId}`} className="text-xs font-bold uppercase tracking-widest text-orange-600">
          Back to serialized project summary
        </Link>
        <span className="text-xs text-neutral-600 uppercase tracking-wide">Live stream: {sseStatus}</span>
      </div>

      <StatusBanner
        items={[
          ...(err ? [{ id: "err", message: err, severity: "error" as const }] : []),
          ...(actionErr ? [{ id: "action", message: actionErr, severity: "error" as const }] : []),
          ...(actionMsg ? [{ id: "action-ok", message: actionMsg, severity: "info" as const }] : []),
          ...(cancelling
            ? [{ id: "cancelling", message: `Cancelling run #${runIdNum}…`, severity: "warning" as const }]
            : []),
          ...(retrying
            ? [{ id: "retrying", message: `Starting retry from run #${runIdNum}…`, severity: "warning" as const }]
            : []),
          ...(sseStatus === "error"
            ? [{ id: "sse", message: "Live stream disconnected — showing polled data.", severity: "warning" as const }]
            : []),
        ]}
        onDismiss={(id) => {
          if (id === "action") setActionErr(null);
          if (id === "action-ok") setActionMsg(null);
        }}
      />
      {cleanupMsg && <div className="text-sm text-neutral-700">{cleanupMsg}</div>}

      <div className="glass p-5 border-orange-300/70 ring-2 ring-orange-100 space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <p className="heading-sub mb-1">Live project run</p>
            <h1 className="heading-main text-xl">Run #{runIdNum}</h1>
            <p className="text-sm text-neutral-600 mt-2">
              {status === "COMPLETED"
                ? "Execution finished. Review results, changed files, verification, and preview the implementation."
                : status === "FAILED" || status === "CANCELLED"
                  ? "Execution stopped. Review errors, then retry to continue from the first incomplete task."
                  : "Track tasks on the timeline below. Click any task to open its full-page trace and context."}
            </p>
            {continueFromTask && ["FAILED", "CANCELLED", "COMPLETED"].includes(status) && (
              <p className="text-sm text-orange-800 mt-2 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2">
                Retry will skip tasks 1–{continueFromTask.index - 1} and continue at task {continueFromTask.index}:{" "}
                <span className="font-semibold">{continueFromTask.name}</span>
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={cancelling || retrying}
              className="px-3 py-1.5 rounded border border-neutral-400 text-[10px] font-bold uppercase tracking-widest text-neutral-600 disabled:opacity-50"
              onClick={async () => {
                setActionErr(null);
                setActionMsg(null);
                setCancelling(true);
                try {
                  const result = await api.cancelProjectRun(projectId, runIdNum);
                  const nextStatus = String(result.status ?? "CANCELLED").toUpperCase();
                  setActionMsg(
                    nextStatus === "CANCEL_REQUESTED"
                      ? `Cancel requested for run #${runIdNum}. It will stop shortly.`
                      : `Run #${runIdNum} cancelled.`,
                  );
                  await refresh();
                } catch (ex: unknown) {
                  setActionErr(ex instanceof Error ? ex.message : String(ex));
                } finally {
                  setCancelling(false);
                }
              }}
            >
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
            <button
              type="button"
              disabled={cancelling || retrying}
              className="px-3 py-1.5 rounded border border-orange-600 text-[10px] font-bold uppercase tracking-widest text-orange-700 disabled:opacity-50"
              onClick={async () => {
                setActionErr(null);
                setActionMsg(null);
                setRetrying(true);
                try {
                  const result = await api.retryProjectRun(projectId, runIdNum);
                  const nextRunId = result.run?.agent_run_id;
                  if (result.already_running && nextRunId) {
                    setActionMsg(result.message ?? `Project already has active run #${nextRunId}.`);
                    navigate(`/projects/${projectId}/runs/${nextRunId}`);
                    return;
                  }
                  if (nextRunId) {
                    setActionMsg(
                      result.message ??
                        `Retry started as run #${nextRunId}, continuing from the last incomplete task.`,
                    );
                    navigate(`/projects/${projectId}/runs/${nextRunId}`);
                    return;
                  }
                  setActionErr("Retry submitted, but no run id was returned.");
                  await refresh();
                } catch (ex: unknown) {
                  setActionErr(ex instanceof Error ? ex.message : String(ex));
                } finally {
                  setRetrying(false);
                }
              }}
            >
              {retrying ? "Retrying…" : "Retry"}
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-red-300 text-[10px] font-bold uppercase tracking-widest text-red-700 hover:bg-red-50"
              onClick={async () => {
                const confirmed = window.confirm(
                  "Remove this run and clean up its git worktree, branch, and local run artifacts? This uses git only (no agent).",
                );
                if (!confirmed) return;
                setCleanupMsg(null);
                try {
                  const result = await api.cleanupProjectRun(projectId, runIdNum, { delete_record: true });
                  setCleanupMsg(
                    result.git?.ok === false
                      ? "Run record removed; some git cleanup steps reported issues — check the repo manually."
                      : "Run removed and workspace cleaned (worktree, branch, artifacts).",
                  );
                  navigate(`/projects/${projectId}`);
                } catch (ex: unknown) {
                  setCleanupMsg(ex instanceof Error ? ex.message : String(ex));
                }
              }}
            >
              Remove &amp; clean up
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-orange-600 text-[10px] font-bold uppercase tracking-widest text-orange-600"
              onClick={() => refresh().catch((e) => setActionErr(String((e as Error).message ?? e)))}
            >
              Refresh
            </button>
            <Link
              to={`/projects/${projectId}/review`}
              className="px-3 py-1.5 rounded bg-neutral-900 text-[10px] font-bold uppercase tracking-widest text-white"
            >
              Review and quick prompt
            </Link>
            <button
              type="button"
              className="px-3 py-1.5 rounded bg-orange-600 text-[10px] font-bold uppercase tracking-widest text-white"
              onClick={async () => {
                setActionErr(null);
                try {
                  const preview = await api.startProjectPreview(projectId);
                  const url = String(preview.preview_url ?? "");
                  if (url) window.open(url, "_blank", "noopener,noreferrer");
                  setPreviewMsg(preview.ok ? "Preview launched." : String(preview.error ?? "Preview command not configured."));
                } catch (ex: unknown) {
                  setActionErr(ex instanceof Error ? ex.message : String(ex));
                }
              }}
            >
              Run app preview
            </button>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            ["Status", status],
            ["Complete", `${completionPercent}%`],
            [
              "Elapsed",
              runStartMs
                ? durationLabelMs(
                    runStartMs,
                    ["COMPLETED", "FAILED", "CANCELLED"].includes(status) ? runEndMs : null,
                  )
                : durationLabel(start, ["COMPLETED", "FAILED", "CANCELLED"].includes(status) ? finish : null),
            ],
            ["Tasks", `${completedTasks.length}/${timelineEntries.length || 1}`],
            ["Errors", String(errorEvents.length + failedTasks.length)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-neutral-300 bg-paper-field p-3">
              <p className="heading-sub text-[9px]">{label}</p>
              <p className="stat-number text-xl">{value}</p>
            </div>
          ))}
        </div>

        <div className="h-2 rounded-full bg-neutral-200 overflow-hidden">
          <div className="h-full bg-orange-600 transition-all" style={{ width: `${completionPercent}%` }} />
        </div>

        {(longRun || retryEvents.length > 0 || errorEvents.length > 0 || resultErrors.length > 0 || resultWarnings.length > 0 || previewMsg) && (
          <div className="grid md:grid-cols-2 gap-3 text-sm">
            {longRun && (
              <div className="rounded-lg border border-orange-300 bg-orange-50 p-3 text-orange-800">
                Long run alert: this run has been active for{" "}
                {runStartMs ? durationLabelMs(runStartMs) : durationLabel(start)}.
              </div>
            )}
            {retryEvents.length > 0 && (
              <div className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-neutral-700">
                Retry activity detected: {retryEvents.length} retry event{retryEvents.length === 1 ? "" : "s"}.
              </div>
            )}
            {errorEvents.length > 0 && (
              <div className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-neutral-700">
                Error activity detected: {errorEvents.length} event{errorEvents.length === 1 ? "" : "s"} need review.
              </div>
            )}
            {resultErrors.map((error) => (
              <div key={error} className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-neutral-800">
                Run error: {error}
              </div>
            ))}
            {resultWarnings.map((warning) => (
              <div key={warning} className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-orange-800">
                Run warning: {warning}
              </div>
            ))}
            {previewMsg && <div className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-neutral-700">{previewMsg}</div>}
          </div>
        )}
      </div>

      {activeTaskRow && (
        <div className="glass p-4 border-orange-200 bg-orange-50/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="heading-sub text-[9px]">Active focus</p>
            <p className="text-sm font-bold text-neutral-900 mt-1">{activeTaskRow.name}</p>
            <p className="text-xs text-neutral-600 mt-1 line-clamp-2">{activeTaskRow.referenceSnippet}</p>
          </div>
          <div className="flex items-center gap-3">
            <TaskStatusBadge status={activeTaskRow.status} kind={activeTaskRow.statusKind} />
            <Link
              to={`/projects/${projectId}/runs/${runIdNum}/tasks/${activeTaskRow.taskId}`}
              className="px-4 py-2 rounded-lg bg-orange-600 text-white text-[10px] font-bold uppercase tracking-widest hover:bg-orange-500"
            >
              Open task monitor
            </Link>
          </div>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <RunTaskTimeline
          projectId={projectId}
          runId={runIdNum}
          run={run}
          tasks={tasks}
          events={events}
          documents={documents}
        />

        <div className="grid lg:grid-cols-2 gap-6">
          <div className="glass p-4 border-neutral-200 lg:col-span-2 xl:col-span-1">
            <h2 className="heading-sub mb-3">Live activity</h2>
            <div className="max-h-[420px] overflow-y-auto divide-y divide-neutral-200">
              {recentEvents.map((event) => (
                <div key={event.agent_event_id} className="py-2 text-xs">
                  <p className="text-neutral-800 font-medium">
                    {event.event_type.replace(/_/g, " ")} / {event.created_at ?? ""}
                  </p>
                  <p className="text-neutral-600 mt-1">{eventMessage(event)}</p>
                </div>
              ))}
              {recentEvents.length === 0 && <p className="text-xs text-neutral-600">No events yet.</p>}
            </div>
          </div>

          <div className="glass p-4 border-neutral-200">
            <h2 className="heading-sub mb-3">Commands</h2>
            <ul className="space-y-2 text-xs">
              {commandEvents.map((event) => (
                <li key={event.agent_event_id} className="border border-neutral-300 rounded-lg p-2">
                  <p className="text-neutral-800">{eventMessage(event)}</p>
                  <p className="text-neutral-600">{event.created_at}</p>
                </li>
              ))}
              {commandEvents.length === 0 && <li className="text-neutral-600">No command events yet.</li>}
            </ul>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="glass p-4 border-neutral-200 lg:col-span-2">
          <h2 className="heading-sub mb-3">Task queue</h2>
          <ul className="space-y-2">
            {timelineEntries.map((row) => (
              <li key={row.key}>
                <Link
                  to={`/projects/${projectId}/runs/${runIdNum}/tasks/${row.taskId}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-neutral-300 bg-paper-field px-3 py-2 hover:border-orange-300 hover:bg-orange-50/30 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-neutral-900 truncate">{row.name}</p>
                    <p className="text-[11px] text-neutral-600">{row.agent} · {row.progress}%</p>
                  </div>
                  <TaskStatusBadge status={row.status} kind={row.statusKind} compact />
                </Link>
              </li>
            ))}
            {timelineEntries.length === 0 && (
              <li className="text-sm text-neutral-600">No tasks attached yet.</li>
            )}
          </ul>
        </div>

        <div className="glass p-4 border-neutral-200 space-y-4">
          <h2 className="heading-sub">What is left</h2>
          <ul className="space-y-2 text-sm">
            {timelineEntries
              .filter((row) => row.progress < 100)
              .slice(0, 8)
              .map((row) => (
                <li key={row.key}>
                  <Link
                    to={`/projects/${projectId}/runs/${runIdNum}/tasks/${row.taskId}`}
                    className="block rounded border border-neutral-300 bg-paper-field p-2 hover:border-orange-300"
                  >
                    <p className="font-semibold text-neutral-800">{row.name}</p>
                    <p className="text-xs text-neutral-600">
                      {row.status.toLowerCase()} / {row.progress}% complete
                    </p>
                  </Link>
                </li>
              ))}
          </ul>
          <h2 className="heading-sub pt-2">Referenced context</h2>
          <ul className="space-y-2 text-xs">
            {referencedDocuments.map((doc) => (
              <li key={doc.document_id} className="rounded border border-neutral-300 bg-paper-field p-2">
                <p className="font-semibold text-neutral-800">{doc.document_name}</p>
                <p className="text-neutral-600">{doc.serialization_status ?? "RAG context"} / {doc.embedding_status ?? "queued"}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="glass p-4 border-neutral-200">
        <h2 className="heading-sub mb-3">Artifacts and changed files</h2>
        <ul className="space-y-2 text-xs max-h-[260px] overflow-y-auto">
          {artifacts.map((artifact) => (
            <li key={artifact.agent_artifact_id} className="border border-neutral-300 rounded-lg p-2">
              <p className="text-neutral-800">{artifact.artifact_name || "artifact"}</p>
              <p className="text-neutral-600">{artifact.artifact_type} / {artifact.size_bytes ?? 0} bytes</p>
            </li>
          ))}
          {changes.map((change) => (
            <li key={change.git_change_id} className="border border-neutral-300 rounded-lg p-2">
              <p className="text-neutral-800">{change.change_type || "M"} / {change.file_path || "(summary)"}</p>
              {change.branch_name && <p className="text-neutral-600">{change.branch_name} {"<-"} {change.base_branch}</p>}
            </li>
          ))}
          {artifacts.length === 0 && changes.length === 0 && <li className="text-neutral-600">No artifacts or file changes recorded yet.</li>}
        </ul>
      </div>

      {Object.keys(designFidelity).length > 0 && !designFidelity.skipped && (
        <div className="glass p-4 border-neutral-200">
          <h2 className="heading-sub mb-3">Design fidelity</h2>
          <div className="text-xs space-y-2">
            <p className={designFidelity.structural_pass ? "text-green-800 font-semibold" : "text-red-800 font-semibold"}>
              Structural: {designFidelity.structural_pass ? "PASS" : "FAIL"}
              {Array.isArray(designFidelity.blocking_failures) && designFidelity.blocking_failures.length > 0
                ? ` (${(designFidelity.blocking_failures as string[]).join(", ")})`
                : ""}
            </p>
            {asRecord(designFidelity.stock_photos).hits && (
              <p className="text-neutral-700">
                Stock photos: {(asRecord(designFidelity.stock_photos).hits as unknown[])?.length ? "detected" : "none"}
              </p>
            )}
            {asRecord(designFidelity.visual_fidelity).sections && (
              <div>
                <p className="font-semibold text-neutral-800 mt-2">Visual (advisory)</p>
                <ul className="list-disc pl-4 text-neutral-600">
                  {(asRecord(designFidelity.visual_fidelity).sections as Array<Record<string, unknown>>).map((s) => (
                    <li key={String(s.slug)}>
                      {String(s.slug)}: {String(s.note ?? s.score ?? "—")}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="glass p-4 border-neutral-200">
        <h2 className="heading-sub mb-3">Verification and review</h2>
        {Object.keys(featureReviewRecord).length > 0 && (
          <div className="mb-4 rounded-lg border border-orange-200 bg-orange-50 p-3 text-xs text-orange-900">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
              <div>
                <p className="heading-sub text-[9px] text-orange-800">Feature-level quality review</p>
                <p className="mt-1 font-semibold">
                  {textValue(featureReviewRecord.recommendation, "needs review").replace(/_/g, " ")}
                </p>
                <p className="mt-1 text-orange-800">{textValue(featureReviewRecord.summary, "No review summary was stored.")}</p>
              </div>
              <div className="text-right">
                <p>{featureContextUsed.length} context items</p>
                <p>{featureDesignRefs.length} design references</p>
              </div>
            </div>
            {featureDesignGaps.length > 0 && (
              <div className="mt-3 rounded border border-orange-300 bg-paper-bright p-2">
                <p className="font-semibold text-neutral-900">Design adherence gaps</p>
                <ul className="mt-1 list-disc pl-5 text-neutral-700">
                  {featureDesignGaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {!review ? (
          <p className="text-xs text-neutral-600">No review payload recorded yet.</p>
        ) : (
          <ul className="space-y-2 text-xs">
            {(review.checks ?? []).map((check) => (
              <li key={check.check} className="border border-neutral-300 rounded-lg p-2 flex justify-between gap-3">
                <span className="text-neutral-800">{check.check}</span>
                <span className={check.ok ? "text-orange-700" : "text-neutral-700"}>
                  {String(check.value)} / {check.ok ? "ok" : "fail"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
