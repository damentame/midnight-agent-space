import type { ProjectProgress } from "../api";
import LoadingButton from "./LoadingButton";

type Props = {
  progress: ProjectProgress | null;
  previewUrl?: string | null;
  onPromote?: () => void;
  promoting?: boolean;
};

const MILESTONE_ICON: Record<string, string> = {
  completed: "✓",
  in_progress: "…",
  pending: "○",
};

const MILESTONE_CLASS: Record<string, string> = {
  completed: "border-green-300 bg-green-50 text-green-800",
  in_progress: "border-orange-300 bg-orange-50 text-orange-800",
  pending: "border-neutral-300 bg-paper-field text-neutral-600",
};

export default function ProgressDashboard({ progress, previewUrl, onPromote, promoting }: Props) {
  if (!progress) {
    return <p className="text-xs text-neutral-500">Progress not available yet.</p>;
  }

  const percent = Math.max(0, Math.min(100, Math.round(progress.percent_complete ?? 0)));
  const milestones = progress.milestones ?? [];
  const risks = progress.risks ?? [];

  return (
    <div className="rounded-lg border border-neutral-300 bg-paper-field p-4 space-y-4">
      <div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Milestone progress</p>
          <span className="text-sm font-bold text-neutral-900">
            {percent}% · {progress.completed_task_count}/{progress.total_tasks} tasks
          </span>
        </div>
        <div className="mt-2 h-2 rounded-full bg-neutral-200 overflow-hidden">
          <div className="h-full bg-orange-600 transition-all" style={{ width: `${percent}%` }} />
        </div>
      </div>

      {milestones.length > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-2">Milestones</p>
          <ul className="space-y-1.5">
            {milestones.map((milestone) => {
              const status = String(milestone.status ?? "pending");
              return (
                <li
                  key={milestone.index}
                  className={`flex items-center justify-between gap-2 rounded border px-2 py-1.5 text-xs ${
                    MILESTONE_CLASS[status] ?? MILESTONE_CLASS.pending
                  }`}
                >
                  <span className="font-semibold flex items-center gap-2">
                    <span aria-hidden="true">{MILESTONE_ICON[status] ?? MILESTONE_ICON.pending}</span>
                    {milestone.name}
                  </span>
                  <span className="shrink-0">
                    {milestone.completed_count}/{milestone.task_count} tasks · target {milestone.percent_target}%
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {risks.length > 0 && (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-900">
          <p className="font-semibold">Risks</p>
          <ul className="mt-1 list-disc pl-4 space-y-0.5">
            {risks.map((risk, index) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        </div>
      )}

      {previewUrl && (
        <div>
          <div className="flex items-center justify-between gap-2 mb-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Live preview (mas/preview)</p>
            {onPromote && (
              <LoadingButton
                loading={Boolean(promoting)}
                loadingLabel="Promoting…"
                disabled={Boolean(promoting) || percent < 100}
                onClick={onPromote}
                title={percent < 100 ? "Available once all milestones are complete" : undefined}
                className="px-3 py-1.5 rounded border border-orange-600 text-orange-700 text-[10px] font-bold uppercase tracking-widest hover:bg-orange-50 disabled:opacity-50"
              >
                Promote to main
              </LoadingButton>
            )}
          </div>
          <iframe
            title="Milestone preview"
            src={previewUrl}
            className="w-full h-72 rounded border border-neutral-300 bg-white"
          />
        </div>
      )}

      <p className="text-[10px] text-neutral-400">Updated {new Date(progress.generated_at).toLocaleString()}</p>
    </div>
  );
}
