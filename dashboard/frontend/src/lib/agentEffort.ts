import type { ProjectTask } from "../api";

export type AgentEffort = {
  level?: string;
  score?: number;
  rationale?: string;
  execution_complexity?: string;
};

export function agentEffortFromTask(task: ProjectTask): AgentEffort {
  const td = task.task_data ?? {};
  const effort = (td.agent_effort as AgentEffort | undefined) ?? {};
  return {
    level: effort.level ?? "medium",
    score: typeof effort.score === "number" ? effort.score : undefined,
    rationale: effort.rationale,
    execution_complexity: effort.execution_complexity,
  };
}

export function effortBadgeClass(level?: string): string {
  const value = (level || "medium").toLowerCase();
  if (value === "low") return "border-neutral-300 bg-paper-field text-neutral-600";
  if (value === "high") return "border-orange-400 bg-orange-50 text-orange-800";
  return "border-orange-200 bg-orange-50/70 text-orange-700";
}
