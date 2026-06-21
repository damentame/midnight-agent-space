import type { TaskStatusKind } from "../../lib/runMonitor";

const STYLES: Record<TaskStatusKind, string> = {
  pending: "border-neutral-300 bg-paper-field text-neutral-600",
  queued: "border-neutral-400 bg-neutral-100 text-neutral-700",
  running: "border-orange-400 bg-orange-50 text-orange-800",
  completed: "border-emerald-400 bg-emerald-50 text-emerald-800",
  failed: "border-red-500 bg-red-50 text-red-800",
  cancelled: "border-neutral-400 bg-paper-field text-neutral-600",
  unknown: "border-neutral-300 bg-paper-field text-neutral-600",
};

const LABELS: Record<TaskStatusKind, string> = {
  pending: "Pending",
  queued: "Queued",
  running: "Running",
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  unknown: "Unknown",
};

type Props = {
  status: string;
  kind: TaskStatusKind;
  compact?: boolean;
  stalled?: boolean;
};

export default function TaskStatusBadge({ status, kind, compact, stalled }: Props) {
  const label =
    kind === "running" && stalled ? "Stalled" : kind === "running" ? "Running" : LABELS[kind];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-bold uppercase tracking-widest ${
        compact ? "px-2 py-0.5 text-[9px]" : "px-2.5 py-1 text-[10px]"
      } ${stalled && kind === "running" ? "border-amber-500 bg-amber-50 text-amber-900" : STYLES[kind]} ${
        kind === "running" ? "monitor-pulse" : ""
      }`}
      title={status}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          kind === "running"
            ? stalled
              ? "bg-amber-500"
              : "bg-orange-500"
            : kind === "completed"
              ? "bg-emerald-500"
              : kind === "failed"
                ? "bg-red-600"
                : kind === "queued"
                  ? "bg-neutral-500"
                  : "bg-neutral-400"
        }`}
      />
      {label}
    </span>
  );
}
