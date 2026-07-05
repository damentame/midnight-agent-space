import {
  budgetProgress,
  efficiencyClass,
  efficiencyLabel,
  formatCostUsd,
  formatTokenCount,
  type TokenUsageSummary,
} from "../lib/tokenUsage";

type Props = {
  usage: TokenUsageSummary | null | undefined;
  title?: string;
  compact?: boolean;
  showModels?: boolean;
  commercialTarget?: number;
};

export default function TokenUsagePanel({
  usage,
  title = "Token usage",
  compact = false,
  showModels = true,
  commercialTarget = 25_000_000,
}: Props) {
  if (!usage?.totals?.total_tokens) {
    return (
      <div className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-xs text-neutral-500">
        {title}: no usage recorded yet.
      </div>
    );
  }

  const totals = usage.totals ?? {};
  const efficiency = usage.efficiency;
  const progress = budgetProgress(totals.total_tokens, commercialTarget);
  const rating = efficiency?.rating;

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-bold uppercase tracking-widest text-neutral-500">{title}</span>
        <span className="font-semibold text-neutral-900">{formatTokenCount(totals.total_tokens)} tokens</span>
        <span className="text-neutral-600">{formatCostUsd(totals.cost_usd)}</span>
        <span className={`rounded px-2 py-0.5 border text-[10px] font-bold uppercase tracking-wider ${efficiencyClass(rating)}`}>
          {efficiencyLabel(rating)}
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-300 bg-paper-field p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">{title}</p>
          <p className="text-lg font-bold text-neutral-900 mt-1">{formatTokenCount(totals.total_tokens)} tokens</p>
          <p className="text-xs text-neutral-600 mt-0.5">
            In {formatTokenCount(totals.input_tokens)} · Out {formatTokenCount(totals.output_tokens)} ·{" "}
            {formatCostUsd(totals.cost_usd)} est.
          </p>
        </div>
        <span className={`rounded px-2 py-1 border text-[10px] font-bold uppercase tracking-wider ${efficiencyClass(rating)}`}>
          {efficiencyLabel(rating)}
        </span>
      </div>

      <div>
        <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-neutral-500">
          <span>Budget vs 25M commercial target</span>
          <span>{progress}%</span>
        </div>
        <div className="mt-1 h-2 rounded-full bg-neutral-200 overflow-hidden">
          <div
            className={`h-full ${progress > 100 ? "bg-red-600" : progress > 70 ? "bg-amber-500" : "bg-green-600"}`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        {efficiency?.multiplier_to_commercial != null && (
          <p className="text-[11px] text-neutral-600 mt-1">
            {efficiency.multiplier_to_commercial}x commercial target
            {efficiency.improvement_vs_110m_baseline_pct != null
              ? ` · ${efficiency.improvement_vs_110m_baseline_pct}% below 110M baseline`
              : ""}
          </p>
        )}
      </div>

      {showModels && (usage.by_model?.length ?? 0) > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-1">By model</p>
          <ul className="space-y-1">
            {usage.by_model!.slice(0, 5).map((row) => (
              <li key={row.model} className="flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-neutral-800">{row.model}</span>
                <span className="text-neutral-600">
                  {formatTokenCount(row.total_tokens)} · {formatCostUsd(row.cost_usd)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(usage.tasks_over_budget ?? 0) > 0 && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          {usage.tasks_over_budget} task(s) exceeded per-task token budget.
        </p>
      )}
    </div>
  );
}
