import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { AgentRun } from "../../api";
import {
  buildTaskTimelineEntries,
  formatTimelineTick,
  timelineWindow,
  type TaskTimelineEntry,
} from "../../lib/runMonitor";
import type { AgentEvent, ProjectDocument } from "../../api";
import TaskStatusBadge from "./TaskStatusBadge";

const BAR_CLASS: Record<TaskTimelineEntry["statusKind"], string> = {
  pending: "bg-neutral-300/70",
  queued: "bg-neutral-400/80",
  running: "bg-orange-500 monitor-bar-running",
  completed: "bg-emerald-500",
  failed: "bg-red-600",
  cancelled: "bg-neutral-500",
  unknown: "bg-neutral-400",
};

type Props = {
  projectId: number;
  runId: number;
  run: AgentRun | null;
  tasks: Record<string, unknown>[];
  events: AgentEvent[];
  documents: ProjectDocument[];
  selectedTaskId?: number | null;
};

export default function RunTaskTimeline({
  projectId,
  runId,
  run,
  tasks,
  events,
  documents,
  selectedTaskId,
}: Props) {
  const nowMs = Date.now();
  const entries = useMemo(
    () =>
      [...buildTaskTimelineEntries(tasks, events, run, documents)].sort(
        (a, b) => a.sequenceIndex - b.sequenceIndex || a.taskId - b.taskId,
      ),
    [tasks, events, run, documents],
  );

  const { originMs, spanMs, nowPercent } = useMemo(
    () => timelineWindow(entries, run, nowMs, events),
    [entries, run, nowMs, events],
  );
  const ticks = useMemo(() => {
    const count = 5;
    return Array.from({ length: count + 1 }, (_, index) => originMs + (spanMs / count) * index);
  }, [originMs, spanMs]);

  const runTerminal = ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED"].includes(String(run?.status ?? "").toUpperCase());

  if (entries.length === 0) {
    return (
      <div className="rounded-xl border border-neutral-300 bg-paper-field p-8 text-center text-sm text-neutral-600">
        No tasks attached to this run yet. Events will appear on the timeline as execution progresses.
      </div>
    );
  }

  return (
    <div className="monitor-timeline-shell rounded-xl border border-neutral-300/90 bg-paper-lift/80 overflow-hidden">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 px-4 py-3 border-b border-neutral-200 bg-paper-field/80">
        <div>
          <p className="heading-sub">Execution timeline</p>
          <p className="text-xs text-neutral-600 mt-1">
            Landscape view of queued, running, and completed tasks. Click a task for full trace and context.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 text-[10px] font-bold uppercase tracking-widest text-neutral-500">
          {(["pending", "queued", "running", "completed", "failed"] as const).map((kind) => (
            <span key={kind} className="inline-flex items-center gap-1.5">
              <span className={`h-2 w-6 rounded-sm ${BAR_CLASS[kind]}`} />
              {kind}
            </span>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[720px] p-4">
          <div className="grid grid-cols-[minmax(180px,220px)_1fr] gap-3 mb-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500">
            <span>Task tree</span>
            <div className="relative h-6">
              {ticks.map((tick, index) => (
                <span
                  key={tick}
                  className="absolute -translate-x-1/2 tabular-nums"
                  style={{ left: `${(index / (ticks.length - 1)) * 100}%` }}
                >
                  {formatTimelineTick(tick, originMs)}
                </span>
              ))}
              {!runTerminal && (
                <span
                  className="absolute top-0 -translate-x-1/2 text-orange-600 text-[9px]"
                  style={{ left: `${nowPercent}%` }}
                >
                  now
                </span>
              )}
            </div>
          </div>

          <div className="relative">
            {!runTerminal && (
              <div
                className="pointer-events-none absolute top-0 bottom-0 z-20 grid grid-cols-[minmax(180px,220px)_1fr] gap-3"
                style={{ left: 0, right: 0 }}
              >
                <div />
                <div className="relative h-full">
                  <div
                    className="absolute top-0 bottom-0 border-l-2 border-dashed border-orange-500/90"
                    style={{ left: `${nowPercent}%` }}
                  />
                </div>
              </div>
            )}

            <div className="relative space-y-2 z-10">
            {entries.map((entry, rowIndex) => {
              const start = entry.startMs ?? originMs;
              const end = entry.endMs ?? (entry.isActive ? nowMs : start + spanMs * 0.08);
              const left = Math.max(0, ((start - originMs) / spanMs) * 100);
              let width = Math.max(2.5, ((end - start) / spanMs) * 100);
              if (entry.isActive) {
                width = Math.min(width, Math.max(2.5, nowPercent - left));
              }
              width = Math.min(width, Math.max(2.5, 100 - left));
              const selected = selectedTaskId === entry.taskId;
              const showConnector = rowIndex > 0 && entry.depth > 0;
              const statusNote = entry.issueMessage
                ? entry.issueMessage
                : entry.isStalled
                  ? "Still running but no new events for 10+ minutes — agent may be stuck."
                  : entry.isActive
                    ? "Running…"
                    : null;

              return (
                <div key={entry.key} className="grid grid-cols-[minmax(180px,220px)_1fr] gap-3 items-center group">
                  <div className="relative pl-2" style={{ paddingLeft: `${8 + entry.depth * 14}px` }}>
                    {showConnector && (
                      <span
                        className="absolute left-2 top-1/2 h-px w-4 bg-neutral-300"
                        aria-hidden
                      />
                    )}
                    {rowIndex > 0 && !showConnector && (
                      <span className="absolute left-3 -top-2 bottom-1/2 w-px bg-neutral-200" aria-hidden />
                    )}
                    <Link
                      to={`/projects/${projectId}/runs/${runId}/tasks/${entry.taskId}`}
                      className={`block rounded-lg border px-3 py-2 transition-colors ${
                        selected
                          ? "border-orange-400 bg-orange-50 ring-2 ring-orange-100"
                          : "border-neutral-300 bg-paper-bright hover:border-orange-300 hover:bg-orange-50/40"
                      }`}
                    >
                      <p className="text-sm font-bold text-neutral-900 truncate">{entry.name}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <TaskStatusBadge status={entry.status} kind={entry.statusKind} compact stalled={entry.isStalled} />
                        {entry.isParallel && (
                          <span className="text-[10px] font-bold uppercase tracking-wider text-violet-700 bg-violet-100 px-1.5 py-0.5 rounded">
                            Parallel
                          </span>
                        )}
                        <span className="text-[10px] text-neutral-500 tabular-nums">{entry.elapsed}</span>
                      </div>
                      {statusNote && (
                        <p
                          className={`mt-1 text-[10px] leading-snug ${
                            entry.statusKind === "failed" || entry.issueMessage
                              ? "text-red-700 font-semibold"
                              : entry.isStalled
                                ? "text-amber-700 font-semibold"
                                : "text-orange-700"
                          }`}
                        >
                          {statusNote}
                        </p>
                      )}
                    </Link>
                  </div>

                  <div className="relative h-12 rounded-lg border border-neutral-200 bg-paper-field/90 overflow-hidden">
                    <div className="absolute inset-0 flex">
                      {ticks.slice(1, -1).map((_, index) => (
                        <div key={index} className="flex-1 border-r border-neutral-200/80 last:border-r-0" />
                      ))}
                    </div>
                    <Link
                      to={`/projects/${projectId}/runs/${runId}/tasks/${entry.taskId}`}
                      className={`absolute top-2 bottom-2 rounded-md shadow-sm transition-all hover:brightness-110 ${BAR_CLASS[entry.statusKind]} ${
                        entry.isStalled ? "ring-2 ring-amber-400" : ""
                      } ${selected ? "ring-2 ring-orange-400 ring-offset-1" : ""}`}
                      style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%` }}
                      title={`${entry.name} — ${entry.status}`}
                    >
                      <span className="sr-only">
                        {entry.name} {entry.status}
                      </span>
                    </Link>
                    {entry.isActive && (
                      <span
                        className="absolute top-1/2 -translate-y-1/2 h-3 w-3 rounded-full bg-orange-500 border-2 border-white monitor-pulse z-10"
                        style={{ left: `calc(${left + Math.min(width, 100 - left)}% - 6px)` }}
                      />
                    )}
                  </div>
                </div>
              );
            })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
