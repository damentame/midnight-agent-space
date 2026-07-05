export type TokenTotals = {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
};

export type TokenEfficiency = {
  rating?: string;
  total_tokens?: number;
  commercial_target?: number;
  excellent_target?: number;
  multiplier_to_commercial?: number | null;
  multiplier_to_excellent?: number | null;
  improvement_vs_110m_baseline_pct?: number;
};

export type TokenUsageByModel = {
  model: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  task_count?: number;
};

export type TokenUsageSummary = {
  totals?: TokenTotals;
  efficiency?: TokenEfficiency;
  by_model?: TokenUsageByModel[];
  by_provider?: Array<Record<string, unknown>>;
  tasks_over_budget?: number;
};

export function extractTokenUsage(source: unknown): TokenUsageSummary | null {
  if (!source || typeof source !== "object") return null;
  const record = source as Record<string, unknown>;
  const direct = record.token_usage;
  if (direct && typeof direct === "object") return direct as TokenUsageSummary;
  const execution = record.execution;
  if (execution && typeof execution === "object") {
    const nested = (execution as Record<string, unknown>).token_usage;
    if (nested && typeof nested === "object") return nested as TokenUsageSummary;
  }
  return null;
}

export function formatTokenCount(value?: number | null): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(Math.round(n));
}

export function formatCostUsd(value?: number | null): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "$0.00";
  if (n < 0.01) return "<$0.01";
  return `$${n.toFixed(2)}`;
}

export function efficiencyLabel(rating?: string): string {
  switch ((rating ?? "").toLowerCase()) {
    case "elite":
      return "Elite";
    case "excellent":
      return "Excellent";
    case "commercial":
      return "On target";
    case "minimum_acceptable":
      return "Minimum acceptable";
    case "over_target":
      return "Over target";
    default:
      return "Not rated";
  }
}

export function efficiencyClass(rating?: string): string {
  switch ((rating ?? "").toLowerCase()) {
    case "elite":
    case "excellent":
    case "commercial":
      return "border-green-300 bg-green-50 text-green-900";
    case "minimum_acceptable":
      return "border-amber-300 bg-amber-50 text-amber-900";
    default:
      return "border-red-300 bg-red-50 text-red-900";
  }
}

export function budgetProgress(totalTokens?: number, target = 25_000_000): number {
  const total = Number(totalTokens ?? 0);
  if (!Number.isFinite(total) || total <= 0 || target <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((total / target) * 100)));
}
