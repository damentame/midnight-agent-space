import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, type CliRuntimeProvider, type ReviewerProvider, type RuntimeCheck } from "../api";
import {
  loadCliRuntime,
  loadSidebarCollapsed,
  saveCliRuntime,
  saveSidebarCollapsed,
} from "../lib/cliRuntime";
import { loadReviewerProvider, saveReviewerProvider } from "../lib/reviewerSettings";
import { loadFigmaApiToken, saveFigmaApiToken } from "../lib/figmaSettings";
import {
  loadFixedModel,
  loadModelSelectionMode,
  saveFixedModel,
  saveModelSelectionMode,
  type ModelSelectionMode,
} from "../lib/modelSettings";

export type SidebarView = "nav" | "settings";

type SettingsContextValue = {
  collapsed: boolean;
  sidebarView: SidebarView;
  cliRuntime: CliRuntimeProvider;
  reviewerProvider: ReviewerProvider;
  modelSelectionMode: ModelSelectionMode;
  fixedModel: string;
  figmaApiToken: string;
  runtimeCheck: RuntimeCheck | null;
  runtimeCheckLoading: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggleCollapsed: () => void;
  setSidebarView: (view: SidebarView) => void;
  setCliRuntime: (provider: CliRuntimeProvider) => void;
  setReviewerProvider: (provider: ReviewerProvider) => void;
  setModelSelectionMode: (mode: ModelSelectionMode) => void;
  setFixedModel: (model: string) => void;
  setFigmaApiToken: (token: string) => void;
  refreshRuntimeCheck: () => Promise<void>;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsedState] = useState(loadSidebarCollapsed);
  const [sidebarView, setSidebarView] = useState<SidebarView>("nav");
  const [cliRuntime, setCliRuntimeState] = useState<CliRuntimeProvider>(loadCliRuntime);
  const [reviewerProvider, setReviewerProviderState] = useState<ReviewerProvider>(loadReviewerProvider);
  const [modelSelectionMode, setModelSelectionModeState] = useState<ModelSelectionMode>(loadModelSelectionMode);
  const [fixedModel, setFixedModelState] = useState<string>(() => loadFixedModel());
  const [figmaApiToken, setFigmaApiTokenState] = useState<string>(() => loadFigmaApiToken());
  const [runtimeCheck, setRuntimeCheck] = useState<RuntimeCheck | null>(null);
  const [runtimeCheckLoading, setRuntimeCheckLoading] = useState(false);

  const refreshRuntimeCheck = useCallback(async () => {
    setRuntimeCheckLoading(true);
    try {
      setRuntimeCheck(await api.runtimeCheck());
    } catch {
      setRuntimeCheck(null);
    } finally {
      setRuntimeCheckLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshRuntimeCheck().catch(() => {});
  }, [refreshRuntimeCheck]);

  const setCollapsed = useCallback((value: boolean) => {
    setCollapsedState(value);
    saveSidebarCollapsed(value);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev;
      saveSidebarCollapsed(next);
      return next;
    });
  }, []);

  const setCliRuntime = useCallback((provider: CliRuntimeProvider) => {
    setCliRuntimeState(provider);
    saveCliRuntime(provider);
  }, []);

  const setReviewerProvider = useCallback((provider: ReviewerProvider) => {
    setReviewerProviderState(provider);
    saveReviewerProvider(provider);
  }, []);

  const setModelSelectionMode = useCallback((mode: ModelSelectionMode) => {
    setModelSelectionModeState(mode);
    saveModelSelectionMode(mode);
  }, []);

  const setFixedModel = useCallback((model: string) => {
    setFixedModelState(model);
    saveFixedModel(model);
  }, []);

  const setFigmaApiToken = useCallback((token: string) => {
    setFigmaApiTokenState(token);
    saveFigmaApiToken(token);
  }, []);

  const value = useMemo(
    () => ({
      collapsed,
      sidebarView,
      cliRuntime,
      reviewerProvider,
      modelSelectionMode,
      fixedModel,
      figmaApiToken,
      runtimeCheck,
      runtimeCheckLoading,
      setCollapsed,
      toggleCollapsed,
      setSidebarView,
      setCliRuntime,
      setReviewerProvider,
      setModelSelectionMode,
      setFixedModel,
      setFigmaApiToken,
      refreshRuntimeCheck,
    }),
    [
      collapsed,
      sidebarView,
      cliRuntime,
      reviewerProvider,
      modelSelectionMode,
      fixedModel,
      figmaApiToken,
      runtimeCheck,
      runtimeCheckLoading,
      setCollapsed,
      toggleCollapsed,
      setCliRuntime,
      setReviewerProvider,
      setModelSelectionMode,
      setFixedModel,
      setFigmaApiToken,
      refreshRuntimeCheck,
    ],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used within SettingsProvider");
  }
  return context;
}
