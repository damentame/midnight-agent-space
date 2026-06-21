import type { ReviewerProvider } from "../api";

const REVIEWER_KEY = "mas.reviewerProvider";

export function loadReviewerProvider(fallback: ReviewerProvider = "claude-cli"): ReviewerProvider {
  try {
    const value = localStorage.getItem(REVIEWER_KEY);
    return value === "codex-cli" ? "codex-cli" : value === "claude-cli" ? "claude-cli" : fallback;
  } catch {
    return fallback;
  }
}

export function saveReviewerProvider(provider: ReviewerProvider): void {
  localStorage.setItem(REVIEWER_KEY, provider);
}

export function resolveReviewerProvider(
  prefs: Record<string, unknown> | undefined,
  fallback: ReviewerProvider,
): ReviewerProvider {
  if (!prefs) return fallback;
  const value = String(prefs.reviewer_provider ?? "");
  return value === "codex-cli" ? "codex-cli" : value === "claude-cli" ? "claude-cli" : fallback;
}
