import type { CliRuntimeProvider } from "../api";

export const CLI_RUNTIME_OPTIONS: { id: CliRuntimeProvider; label: string; description: string }[] = [
  {
    id: "codex-cli",
    label: "Codex CLI",
    description: "OpenAI Codex agent in the terminal (codex exec).",
  },
  {
    id: "claude-cli",
    label: "Claude CLI",
    description: "Anthropic Claude Code agent in the terminal (claude -p).",
  },
  {
    id: "cursor-agent",
    label: "Cursor Agent",
    description: "Cursor Agent CLI for code-focused implementation (cursor-agent -p).",
  },
];

const STORAGE_KEY = "mas.cliRuntime";
const SIDEBAR_COLLAPSED_KEY = "mas.sidebarCollapsed";

export function loadCliRuntime(): CliRuntimeProvider {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "claude-cli") return "claude-cli";
    if (value === "cursor-agent") return "cursor-agent";
    return "codex-cli";
  } catch {
    return "codex-cli";
  }
}

export function saveCliRuntime(provider: CliRuntimeProvider): void {
  localStorage.setItem(STORAGE_KEY, provider);
}

export function loadSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveSidebarCollapsed(collapsed: boolean): void {
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
}

export function resolveCliRuntimeProvider(
  prefs: Record<string, unknown> | undefined,
  fallback: CliRuntimeProvider,
): CliRuntimeProvider {
  if (!prefs) return fallback;
  const value = String(prefs.provider ?? prefs.runtime ?? "");
  if (value === "claude-cli") return "claude-cli";
  if (value === "cursor-agent") return "cursor-agent";
  if (value === "codex-cli") return "codex-cli";
  return fallback;
}

export function runtimeLabel(provider: CliRuntimeProvider): string {
  return CLI_RUNTIME_OPTIONS.find((option) => option.id === provider)?.label ?? provider;
}
