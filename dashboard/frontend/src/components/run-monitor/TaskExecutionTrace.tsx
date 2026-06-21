import type { AgentEvent } from "../../api";
import { eventMessage, textValue } from "../../lib/runMonitor";
import TaskStatusBadge from "./TaskStatusBadge";
import type { TaskStatusKind } from "../../lib/runMonitor";

function tracePhase(eventType: string): string {
  const type = eventType.toUpperCase();
  if (type.startsWith("TASK_")) return "Task lifecycle";
  if (type.includes("COMMAND") || type.includes("STDOUT") || type.includes("STDERR")) return "CLI execution";
  if (type.includes("ERROR") || type.includes("FAIL")) return "Errors";
  if (type.startsWith("RUN_")) return "Run";
  return "Activity";
}

type Props = {
  events: AgentEvent[];
  statusKind: TaskStatusKind;
  status: string;
  currentActivity?: string;
};

export default function TaskExecutionTrace({ events, statusKind, status, currentActivity }: Props) {
  const reversed = [...events].reverse();

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-orange-200 bg-orange-50/70 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="heading-sub text-[9px] text-orange-800">Current activity</p>
            <p className="text-sm text-neutral-900 mt-1">
              {currentActivity || (statusKind === "running" ? "Agent is executing this task…" : "No live activity for this task.")}
            </p>
          </div>
          <TaskStatusBadge status={status} kind={statusKind} />
        </div>
      </div>

      <div>
        <p className="heading-sub mb-3">Execution trace</p>
        <div className="relative max-h-[520px] overflow-y-auto pr-2">
          <div className="absolute left-[11px] top-2 bottom-2 w-px bg-neutral-300" aria-hidden />
          <ul className="space-y-3">
            {reversed.map((event, index) => {
              const phase = tracePhase(event.event_type);
              const isLatest = index === 0 && statusKind === "running";
              return (
                <li key={event.agent_event_id} className="relative pl-8">
                  <span
                    className={`absolute left-1.5 top-2 h-3 w-3 rounded-full border-2 border-white ${
                      isLatest ? "bg-orange-500 monitor-pulse" : "bg-neutral-400"
                    }`}
                  />
                  <div
                    className={`rounded-lg border p-3 text-xs ${
                      isLatest ? "border-orange-300 bg-orange-50/50" : "border-neutral-300 bg-paper-bright"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-bold text-neutral-900">{event.event_type.replace(/_/g, " ")}</p>
                      <span className="text-[10px] uppercase tracking-widest text-neutral-500">{phase}</span>
                    </div>
                    <p className="text-[10px] text-neutral-500 mt-1 tabular-nums">{event.created_at ?? ""}</p>
                    <p className="text-neutral-700 mt-2 leading-relaxed">{eventMessage(event)}</p>
                    {textValue(event.event_payload?.model, "") && (
                      <p className="text-[10px] text-neutral-500 mt-1">Model: {textValue(event.event_payload?.model)}</p>
                    )}
                  </div>
                </li>
              );
            })}
            {events.length === 0 && (
              <li className="text-sm text-neutral-600 pl-8">No task-specific events recorded yet.</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
