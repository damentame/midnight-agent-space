import { useEffect, useMemo, useState } from "react";
import type { CliRuntimeProvider, ReviewerProvider } from "../api";
import { api } from "../api";
import { useSettings } from "../context/SettingsContext";
import { CLI_RUNTIME_OPTIONS } from "../lib/cliRuntime";
import { maskFigmaToken } from "../lib/figmaSettings";
import { modelSelectionLabel, type ModelSelectionMode } from "../lib/modelSettings";

export default function SidebarSettings() {
  const {
    cliRuntime,
    setCliRuntime,
    reviewerProvider,
    setReviewerProvider,
    modelSelectionMode,
    setModelSelectionMode,
    fixedModel,
    setFixedModel,
    runtimeCheck,
    runtimeCheckLoading,
    figmaApiToken,
    setFigmaApiToken,
    refreshRuntimeCheck,
  } = useSettings();

  const [figmaTokenDraft, setFigmaTokenDraft] = useState(figmaApiToken);
  const [figmaTokenStatus, setFigmaTokenStatus] = useState<string | null>(null);
  const [figmaValidating, setFigmaValidating] = useState(false);

  useEffect(() => {
    setFigmaTokenDraft(figmaApiToken);
  }, [figmaApiToken]);

  const catalog = runtimeCheck?.model_catalog as
    | {
        selection_modes?: { id: string; label: string; description: string }[];
        providers?: Record<
          string,
          { label: string; optimized: { fast: string; complex: string }; suggested_models: string[] }
        >;
      }
    | undefined;

  const providerCatalog = catalog?.providers?.[cliRuntime];
  const suggestedModels = providerCatalog?.suggested_models ?? [];
  const optimized = providerCatalog?.optimized;

  const defaultFixedModel = useMemo(() => {
    if (suggestedModels.length > 0) return suggestedModels[Math.min(1, suggestedModels.length - 1)];
    if (cliRuntime === "claude-cli") return "sonnet";
    if (cliRuntime === "cursor-agent") return "composer-2.5";
    return "gpt-4.1-mini";
  }, [cliRuntime, suggestedModels]);

  useEffect(() => {
    if (!fixedModel && defaultFixedModel) {
      setFixedModel(defaultFixedModel);
    }
  }, [defaultFixedModel, fixedModel, setFixedModel]);

  return (
    <div className="space-y-4 p-3">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Agent runtime</p>
        <p className="text-xs text-neutral-600 mt-1 leading-relaxed">
          CLI provider and model strategy for project execution.
        </p>
      </div>

      <div className="space-y-2">
        {CLI_RUNTIME_OPTIONS.map((option) => {
          const status = runtimeCheck?.cli_runtimes?.find((row) => row.id === option.id);
          const installed = status?.found ?? false;
          const selected = cliRuntime === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setCliRuntime(option.id as CliRuntimeProvider)}
              className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
                selected
                  ? "border-orange-400 bg-orange-50 text-orange-900"
                  : "border-neutral-300 bg-paper-bright text-neutral-800 hover:border-orange-300"
              }`}
            >
              <p className="text-xs font-bold uppercase tracking-widest">{option.label}</p>
              <p className="text-[11px] mt-1 text-neutral-600 leading-snug">{option.description}</p>
              <p className="text-[10px] mt-1.5 font-bold uppercase tracking-widest text-neutral-500">
                {runtimeCheckLoading
                  ? "Checking…"
                  : installed
                    ? option.id === "cursor-agent"
                      ? "Installed"
                      : option.id === "claude-cli"
                        ? "Installed"
                        : "On PATH"
                    : "Not detected"}
              </p>
            </button>
          );
        })}
      </div>

      <div className="border-t border-neutral-300/80 pt-3 space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Model strategy</p>
        {(catalog?.selection_modes ?? [
          {
            id: "optimized",
            label: "Balanced agent usage",
            description: "Cursor Agent for code tasks, reviewer CLI for review, models by effort.",
          },
          { id: "fixed", label: "Fixed model", description: "Use one runtime/model for all tasks." },
        ]).map((mode) => {
          const selected = modelSelectionMode === mode.id;
          return (
            <button
              key={mode.id}
              type="button"
              onClick={() => setModelSelectionMode(mode.id as ModelSelectionMode)}
              className={`w-full rounded-lg border px-3 py-2 text-left ${
                selected
                  ? "border-orange-400 bg-orange-50 text-orange-900"
                  : "border-neutral-300 bg-paper-bright text-neutral-800 hover:border-orange-300"
              }`}
            >
              <p className="text-xs font-bold uppercase tracking-widest">{mode.label}</p>
              <p className="text-[11px] mt-1 text-neutral-600">{mode.description}</p>
            </button>
          );
        })}
        {modelSelectionMode === "optimized" && (
          <div className="space-y-2">
            <p className="text-[11px] text-neutral-600 rounded-lg border border-orange-200 bg-orange-50/60 px-3 py-2 leading-snug">
              Code tasks → <span className="font-bold">Cursor Agent</span>. Review tasks → reviewer CLI below.
              A post-run design review runs automatically after implementation.
            </p>
            {optimized && (
              <p className="text-[11px] text-neutral-600 rounded-lg border border-neutral-200 bg-paper-field px-3 py-2">
                Low/medium effort → <span className="font-bold">{optimized.fast}</span>. High effort →{" "}
                <span className="font-bold">{optimized.complex}</span>.
              </p>
            )}
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Reviewer CLI</span>
              <select
                className="mt-1 w-full rounded-lg border border-neutral-300 bg-paper-bright px-2 py-2 text-sm text-neutral-900"
                value={reviewerProvider}
                onChange={(e) => setReviewerProvider(e.target.value as ReviewerProvider)}
              >
                <option value="claude-cli">Claude CLI (default)</option>
                <option value="codex-cli">Codex CLI</option>
              </select>
            </label>
          </div>
        )}
        {modelSelectionMode === "fixed" && (
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Model</span>
            <select
              className="mt-1 w-full rounded-lg border border-neutral-300 bg-paper-bright px-2 py-2 text-sm text-neutral-900"
              value={fixedModel || defaultFixedModel}
              onChange={(e) => setFixedModel(e.target.value)}
            >
              {suggestedModels.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="border-t border-neutral-300/80 pt-3 space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Figma API</p>
        <p className="text-[11px] text-neutral-600 leading-snug">
          Personal access token with <span className="font-bold">File content</span> read scope. Stored in this browser only.
        </p>
        <input
          type="password"
          autoComplete="off"
          className="w-full rounded-lg border border-neutral-300 bg-paper-bright px-2 py-2 text-sm text-neutral-900"
          placeholder={figmaApiToken ? maskFigmaToken(figmaApiToken) : "figd_…"}
          value={figmaTokenDraft}
          onChange={(e) => setFigmaTokenDraft(e.target.value)}
        />
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!figmaTokenDraft.trim() || figmaValidating}
            onClick={async () => {
              setFigmaValidating(true);
              setFigmaTokenStatus(null);
              try {
                const result = await api.validateFigmaToken(figmaTokenDraft.trim());
                setFigmaApiToken(figmaTokenDraft.trim());
                setFigmaTokenStatus(
                  result.email ? `Valid (${result.email})` : result.handle ? `Valid (@${result.handle})` : "Valid",
                );
              } catch (ex: unknown) {
                const msg = ex instanceof Error ? ex.message : String(ex);
                setFigmaTokenStatus(
                  msg.includes("Not Found")
                    ? "API route not found — restart the dashboard backend on port 8001, then try again."
                    : msg,
                );
              } finally {
                setFigmaValidating(false);
              }
            }}
            className="flex-1 rounded-lg border border-orange-600 bg-orange-50 px-2 py-2 text-[10px] font-bold uppercase tracking-widest text-orange-800 hover:bg-orange-100 disabled:opacity-50"
          >
            {figmaValidating ? "Checking…" : "Save & test"}
          </button>
          <button
            type="button"
            onClick={() => {
              setFigmaTokenDraft("");
              setFigmaApiToken("");
              setFigmaTokenStatus(null);
            }}
            className="rounded-lg border border-neutral-300 px-2 py-2 text-[10px] font-bold uppercase tracking-widest text-neutral-600 hover:border-orange-300"
          >
            Clear
          </button>
        </div>
        {figmaTokenStatus && (
          <p className="text-[11px] text-neutral-600 rounded-lg border border-neutral-200 bg-paper-field px-2 py-1.5">
            {figmaTokenStatus}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={() => refreshRuntimeCheck()}
        disabled={runtimeCheckLoading}
        className="w-full rounded-lg border border-neutral-300 bg-paper-field px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-neutral-700 hover:border-orange-300 disabled:opacity-50"
      >
        Refresh status
      </button>

      <p className="text-[10px] text-neutral-500 leading-relaxed">
        Active: {modelSelectionLabel(modelSelectionMode)}
        {modelSelectionMode === "fixed" ? ` (${fixedModel || defaultFixedModel})` : ""} · primary{" "}
        {CLI_RUNTIME_OPTIONS.find((o) => o.id === cliRuntime)?.label ?? cliRuntime}
        {modelSelectionMode === "optimized" ? ` · reviewer ${reviewerProvider}` : ""}.
      </p>
    </div>
  );
}
