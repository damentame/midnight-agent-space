import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import TaskDetailPanels from "../components/run-monitor/TaskDetailPanels";
import TaskExecutionTrace from "../components/run-monitor/TaskExecutionTrace";
import TaskStatusBadge from "../components/run-monitor/TaskStatusBadge";
import RunTaskTimeline from "../components/run-monitor/RunTaskTimeline";
import { useRunMonitor } from "../hooks/useRunMonitor";
import {
  asRecord,
  buildTaskTimelineEntries,
  eventsForTask,
  eventMessage,
  textValue,
  timelineWindow,
  timestamp,
} from "../lib/runMonitor";

export default function RunTaskDetail() {
  const { id, runId, taskId } = useParams();
  const projectId = Number(id);
  const runIdNum = Number(runId);
  const taskIdNum = Number(taskId);

  const { run, events, tasks, documents, sseStatus, err, loading, refresh } = useRunMonitor(projectId, runIdNum);

  const entry = useMemo(() => {
    const rows = buildTaskTimelineEntries(tasks, events, run, documents);
    return rows.find((row) => row.taskId === taskIdNum) ?? null;
  }, [tasks, events, run, documents, taskIdNum]);

  const taskEvents = useMemo(() => eventsForTask(taskIdNum, events), [taskIdNum, events]);

  const contextEntries = useMemo(() => {
    const task = entry?.task;
    if (!task) return [];
    const taskContext = asRecord(asRecord(task.task_data).rag_ready_context);
    const taskDocs = taskContext.documents;
    if (Array.isArray(taskDocs)) return taskDocs.map((item) => asRecord(item));
    const packDocs = asRecord(asRecord(run?.context_pack).rag_ready_context).documents;
    if (Array.isArray(packDocs)) return packDocs.map((item) => asRecord(item));
    return [];
  }, [entry?.task, run?.context_pack]);

  const designReferences = useMemo(
    () =>
      contextEntries.filter((item) => {
        const kind = textValue(item.content_kind, "").toLowerCase();
        const preview = textValue(item.text_preview, "").toLowerCase();
        return ["image", "figma_design", "figma_import", "document_asset"].includes(kind) || preview.includes("figma.com");
      }),
    [contextEntries],
  );

  const executionParameters = useMemo(() => {
    const task = entry?.task;
    if (!task) return {};
    return {
      ...asRecord(task.parameters),
      ...asRecord(asRecord(task.task_data).execution_parameters),
    };
  }, [entry?.task]);

  const currentActivity = useMemo(() => {
    const latest = [...taskEvents].reverse().find((event) => {
      const type = String(event.event_type ?? "").toUpperCase();
      return !["TASK_COMPLETED", "TASK_FAILED", "TASK_CANCELLED"].includes(type);
    });
    return latest ? eventMessage(latest) : undefined;
  }, [taskEvents]);

  const taskWindow = useMemo(() => {
    if (!entry) return null;
    const all = buildTaskTimelineEntries(tasks, events, run, documents);
    const { originMs, spanMs } = timelineWindow(all, run, Date.now(), events);
    const start = entry.startMs ?? originMs;
    const end = entry.endMs ?? Date.now();
    return {
      left: ((start - originMs) / spanMs) * 100,
      width: Math.max(4, ((end - start) / spanMs) * 100),
    };
  }, [entry, tasks, events, run, documents]);

  if (!Number.isFinite(projectId) || !Number.isFinite(runIdNum) || !Number.isFinite(taskIdNum)) {
    return <p className="text-sm text-neutral-600">Invalid project, run, or task identifier.</p>;
  }

  if (loading && !entry) {
    return <p className="text-sm text-neutral-600">Loading task monitor…</p>;
  }

  if (!entry) {
    return (
      <div className="space-y-4">
        <Link
          to={`/projects/${projectId}/runs/${runIdNum}`}
          className="text-xs font-bold uppercase tracking-widest text-orange-600"
        >
          Back to live monitor
        </Link>
        <p className="text-sm text-neutral-700">Task #{taskIdNum} was not found for this project.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <Link
            to={`/projects/${projectId}/runs/${runIdNum}`}
            className="text-xs font-bold uppercase tracking-widest text-orange-600"
          >
            Back to run timeline
          </Link>
          <h1 className="heading-main text-xl mt-2">{entry.name}</h1>
          <p className="text-sm text-neutral-600 mt-1">
            Run #{runIdNum} · Task #{taskIdNum} · {entry.agent} · Live stream: {sseStatus}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <TaskStatusBadge status={entry.status} kind={entry.statusKind} />
          <button
            type="button"
            onClick={() => refresh().catch(() => {})}
            className="px-3 py-1.5 rounded border border-neutral-400 text-[10px] font-bold uppercase tracking-widest text-neutral-600"
          >
            Refresh
          </button>
        </div>
      </div>

      {err && <div className="text-sm text-neutral-700">{err}</div>}

      <div className="glass p-4 border-neutral-200 space-y-3">
        <p className="heading-sub">Task timeline on run</p>
        {taskWindow && (
          <div className="relative h-10 rounded-lg border border-neutral-300 bg-paper-field overflow-hidden">
            <div
              className={`absolute top-2 bottom-2 rounded-md ${
                entry.statusKind === "running"
                  ? "bg-orange-500 monitor-bar-running"
                  : entry.statusKind === "completed"
                    ? "bg-emerald-500"
                    : entry.statusKind === "failed"
                      ? "bg-neutral-800"
                      : "bg-neutral-400"
              }`}
              style={{ left: `${taskWindow.left}%`, width: `${taskWindow.width}%` }}
            />
            {taskEvents.map((event) => {
              const at = timestamp(event.created_at);
              if (!at) return null;
              const all = buildTaskTimelineEntries(tasks, events, run, documents);
              const { originMs, spanMs } = timelineWindow(all, run, Date.now(), events);
              const left = ((at - originMs) / spanMs) * 100;
              return (
                <span
                  key={event.agent_event_id}
                  className="absolute top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full bg-white border border-neutral-500"
                  style={{ left: `${left}%` }}
                  title={event.event_type}
                />
              );
            })}
          </div>
        )}
        <p className="text-xs text-neutral-600">
          {entry.progress}% complete · {entry.elapsed} elapsed · {taskEvents.length} trace events
        </p>
      </div>

      <div className="grid xl:grid-cols-[1.1fr_0.9fr] gap-6">
        <TaskExecutionTrace
          events={taskEvents}
          statusKind={entry.statusKind}
          status={entry.status}
          currentActivity={currentActivity}
        />
        <TaskDetailPanels
          task={entry.task}
          run={run}
          contextEntries={contextEntries}
          designReferences={designReferences}
          executionParameters={executionParameters}
          referenceSnippet={entry.referenceSnippet}
        />
      </div>

      <div>
        <p className="heading-sub mb-3">Full run context</p>
        <RunTaskTimeline
          projectId={projectId}
          runId={runIdNum}
          run={run}
          tasks={tasks}
          events={events}
          documents={documents}
          selectedTaskId={taskIdNum}
        />
      </div>
    </div>
  );
}
