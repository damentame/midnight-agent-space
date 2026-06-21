export type ModelSelectionMode = "optimized" | "fixed";

const MODE_KEY = "mas.modelSelectionMode";
const MODEL_KEY = "mas.fixedModel";

export function loadModelSelectionMode(): ModelSelectionMode {
  try {
    const value = localStorage.getItem(MODE_KEY);
    return value === "fixed" ? "fixed" : "optimized";
  } catch {
    return "optimized";
  }
}

export function saveModelSelectionMode(mode: ModelSelectionMode): void {
  localStorage.setItem(MODE_KEY, mode);
}

export function loadFixedModel(fallback = ""): string {
  try {
    return localStorage.getItem(MODEL_KEY) || fallback;
  } catch {
    return fallback;
  }
}

export function saveFixedModel(model: string): void {
  localStorage.setItem(MODEL_KEY, model);
}

export function modelSelectionLabel(mode: ModelSelectionMode): string {
  return mode === "fixed" ? "Fixed model" : "Balanced agent usage";
}

export function agentEffortLabel(level?: string | null): string {
  const value = (level || "medium").toLowerCase();
  if (value === "low") return "Low agent effort";
  if (value === "high") return "High agent effort";
  return "Medium agent effort";
}
