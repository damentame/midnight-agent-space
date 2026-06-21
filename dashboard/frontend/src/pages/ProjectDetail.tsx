import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  type AgentEvent,
  type AgentRun,
  type DesignReadiness,
  type FigmaImportResult,
  type Project,
  type ProjectDocument,
  type ProjectMetadata,
  type ProjectProgress,
  type ProjectTask,
} from "../api";
import ContextLibrary from "../components/ContextLibrary";
import FigmaDesignStatus from "../components/FigmaDesignStatus";
import LoadingButton from "../components/LoadingButton";
import ProgressDashboard from "../components/ProgressDashboard";
import Spinner from "../components/Spinner";
import StatusBanner, { type StatusBannerItem } from "../components/StatusBanner";
import WorkingBanner from "../components/WorkingBanner";
import RepoPathSelector from "../components/RepoPathSelector";
import { slugifyProjectName, waitForCodebaseSerialization } from "../lib/projectWorkspace";
import { useSettings } from "../context/SettingsContext";
import { agentEffortFromTask, effortBadgeClass } from "../lib/agentEffort";
import { runtimeLabel } from "../lib/cliRuntime";
import { modelSelectionLabel } from "../lib/modelSettings";
import { resolveBoardRun, taskStatusFromRunEvents } from "../lib/runMonitor";

type FlowTab = "context" | "serialize" | "execute" | "review";
const FLOW_TABS: FlowTab[] = ["context", "serialize", "execute", "review"];

type PreviewPhase = "idle" | "starting" | "launched" | "ready" | "failed";

type PreviewRuntime = {
  phase: PreviewPhase;
  previewUrl: string;
  openUrl: string;
  command?: string;
  message?: string;
  reachable?: boolean;
  statusCode?: number;
  startedAt?: string;
};

type PreviewStep = {
  id: string;
  label: string;
  status: "pending" | "active" | "done" | "error";
  detail?: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

function docKind(doc: ProjectDocument): string {
  const mime = (doc.file_mime_type ?? "").toLowerCase();
  const ext = (doc.file_extension ?? "").toLowerCase();
  if (mime.startsWith("image/") || [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"].includes(ext)) return "image";
  if ([".fig", ".figma", ".sketch"].includes(ext)) return "design";
  if ([".pdf", ".docx"].includes(ext)) return "document";
  return "text";
}

function taskProgress(status?: string | null): number {
  const value = String(status ?? "").toUpperCase();
  if (["COMPLETED", "DONE", "PASSED"].includes(value)) return 100;
  if (["RUNNING", "STARTED", "IN_PROGRESS", "PROCESSING"].includes(value)) return 55;
  if (["FAILED", "ERROR", "CANCELLED", "BLOCKED"].includes(value)) return 80;
  if (["QUEUED", "READY_FOR_AGENT", "PENDING", "PLANNED"].includes(value)) return 0;
  return 0;
}

function statusClass(status?: string | null): string {
  const value = String(status ?? "").toUpperCase();
  if (["COMPLETED", "DONE", "PASSED"].includes(value)) return "border-green-300 bg-green-50 text-green-800";
  if (["RUNNING", "STARTED", "IN_PROGRESS", "PROCESSING"].includes(value)) return "border-orange-300 bg-orange-50 text-orange-800";
  if (["FAILED", "ERROR", "CANCELLED", "BLOCKED"].includes(value)) return "border-red-300 bg-red-50 text-red-800";
  return "border-neutral-300 bg-paper-field text-neutral-600";
}

export default function ProjectDetail() {
  const { id, tab: tabParam } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const projectId = Number(id);
  const tab: FlowTab = FLOW_TABS.includes(tabParam as FlowTab) ? (tabParam as FlowTab) : "context";
  const [pollErr, setPollErr] = useState<string | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);

  const goToTab = useCallback(
    (next: FlowTab) => {
      navigate(`/projects/${projectId}/${next}`);
    },
    [navigate, projectId],
  );
  const [project, setProject] = useState<Project | null>(null);
  const [metadata, setMetadata] = useState<ProjectMetadata | null>(null);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [boardRunEvents, setBoardRunEvents] = useState<AgentEvent[]>([]);
  const [progress, setProgress] = useState<ProjectProgress | null>(null);
  const [promotingToMain, setPromotingToMain] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<Record<string, unknown> | null>(null);
  const [goal, setGoal] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [workspaceParentPath, setWorkspaceParentPath] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewSummary, setPreviewSummary] = useState<string | null>(null);
  const [previewRuntime, setPreviewRuntime] = useState<PreviewRuntime>({
    phase: "idle",
    previewUrl: "",
    openUrl: "",
  });
  const [previewPollActive, setPreviewPollActive] = useState(false);
  const [previewLaunching, setPreviewLaunching] = useState(false);
  const [previewSteps, setPreviewSteps] = useState<PreviewStep[]>([]);
  const [previewActivity, setPreviewActivity] = useState<string[]>([]);
  const autoPreviewOnce = useRef(false);
  const { cliRuntime, reviewerProvider, modelSelectionMode, fixedModel, figmaApiToken } = useSettings();
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadNotes, setUploadNotes] = useState("");
  const [uploadMaxMb, setUploadMaxMb] = useState(50);
  const [figmaUrl, setFigmaUrl] = useState("");
  const [figmaNotes, setFigmaNotes] = useState("");
  const [designPackFile, setDesignPackFile] = useState<File | null>(null);
  const [designPackNotes, setDesignPackNotes] = useState("");
  const [designPackInputKey, setDesignPackInputKey] = useState(0);
  const [designReadiness, setDesignReadiness] = useState<DesignReadiness | null>(null);
  const [lastFigmaImport, setLastFigmaImport] = useState<FigmaImportResult | null>(null);
  const [docName, setDocName] = useState("");
  const [docText, setDocText] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loadingProject, setLoadingProject] = useState(true);
  const [versionHistory, setVersionHistory] = useState<
    Array<{
      version: number;
      git_tag?: string | null;
      commit_hash?: string | null;
      reason?: string;
      created_at?: string;
    }>
  >([]);
  const [refreshReason, setRefreshReason] = useState(
    "Reset after incorrect design implementation; re-run with Figma assets and balanced agent routing.",
  );

  const load = async () => {
    if (!Number.isFinite(projectId)) return;
    setLoadingProject(true);
    setErr(null);
    try {
    const [projectRow, metadataRow, documentRows, taskRows, runRows, readinessRow] = await Promise.all([
      api.project(projectId),
      api.projectMetadata(projectId),
      api.documents(projectId),
      api.tasks(projectId),
      api.projectRuns(projectId, 25),
      api.getDesignReadiness(projectId).catch(() => null),
    ]);
    setDesignReadiness(readinessRow);
    const prefs = metadataRow.runtime_preferences ?? {};
    setProject(projectRow);
    setMetadata(metadataRow);
    setDocuments(documentRows);
    setTasks(taskRows);
    setRuns(runRows);
    setRepoPath(String(prefs.repo_path ?? ""));
    setWorkspaceParentPath(String(prefs.workspace_parent_path ?? ""));
    const cmd = String(prefs.preview_command ?? "").trim();
    const url = String(prefs.preview_url ?? "").trim();
    setPreviewUrl(url);
    setPreviewSummary(cmd && url ? `${cmd} → ${url}` : cmd ? cmd : null);
    if (url) {
      setPreviewRuntime((prev) => ({
        ...prev,
        previewUrl: url,
        openUrl: url,
      }));
    }
    const session = asRecord(prefs.preview_session);
    const sessionUrl = String(session.preview_url ?? "");
    if (sessionUrl && !sessionUrl.includes(":5173")) {
      setPreviewRuntime({
        phase: "launched",
        previewUrl: sessionUrl,
        openUrl: sessionUrl,
        command: String(session.preview_command ?? cmd),
        message: "Preview was launched earlier. Checking if it is still running…",
      });
      setPreviewPollActive(true);
    }
    setGoal(String(metadataRow.metadata?.analysis_goal ?? projectRow.description ?? ""));
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setLoadingProject(false);
    }
  };

  const appendPreviewActivity = useCallback((line: string) => {
    const stamp = new Date().toLocaleTimeString();
    setPreviewActivity((prev) => [...prev, `${stamp} — ${line}`]);
  }, []);

  const applyPreviewStatus = (status: {
    phase?: string;
    reachable?: boolean;
    preview_url?: string | null;
    final_url?: string;
    preview_command?: string | null;
    message?: string;
    status_code?: number;
  }) => {
    const openUrl = String(status.final_url ?? status.preview_url ?? previewUrl);
    const previewTarget = String(status.preview_url ?? openUrl);
    const apiPhase = String(status.phase ?? "").toLowerCase();
    let phase: PreviewPhase = "idle";
    if (status.reachable || apiPhase === "ready") phase = "ready";
    else if (apiPhase === "launched") phase = "launched";
    else if (previewTarget && apiPhase === "not_started") phase = "idle";
    else if (previewTarget) phase = "launched";

    setPreviewRuntime((prev) => ({
      phase: phase === "idle" && prev.phase === "starting" ? "starting" : phase,
      previewUrl: previewTarget || prev.previewUrl,
      openUrl: openUrl || prev.openUrl,
      command: status.preview_command ?? prev.command,
      message: status.message ?? prev.message,
      reachable: status.reachable,
      statusCode: status.status_code,
    }));
    if (phase === "ready") {
      setPreviewPollActive(false);
      appendPreviewActivity(`App responded at ${openUrl}`);
    }
  };

  useEffect(() => {
    if (searchParams.get("tab") === "history") {
      navigate(`/projects/${projectId}/review`, { replace: true });
    }
  }, [searchParams, projectId, navigate]);

  useEffect(() => {
    void load();
  }, [projectId]);

  useEffect(() => {
    if (!Number.isFinite(projectId)) return;
    api
      .projectHealth(projectId)
      .then(() => setHealthErr(null))
      .catch((e) => setHealthErr(String((e as Error).message ?? e)));
  }, [projectId, runs.length, tasks.length]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !repoPath.trim()) return;
    api
      .detectProjectPreview(projectId)
      .then((detected) => {
        if (detected.ok && detected.preview_command && detected.preview_url && !detected.preview_url.includes(":5173")) {
          setPreviewUrl(detected.preview_url);
          const from = detected.detected_from ? ` (${detected.detected_from})` : "";
          const portHint = detected.port_note ? ` — ${detected.port_note}` : "";
          setPreviewSummary(`${detected.preview_command} → ${detected.preview_url}${from}${portHint}`);
          return;
        }
        if (detected.error) setPreviewSummary(detected.error);
      })
      .catch((e) => setPollErr(`Preview detection failed: ${String((e as Error).message ?? e)}`));
  }, [projectId, repoPath]);

  useEffect(() => {
    api
      .uploadSettings()
      .then((s) => setUploadMaxMb(s.max_size_mb))
      .catch((e) => setPollErr(`Could not load upload settings: ${String((e as Error).message ?? e)}`));
  }, []);

  useEffect(() => {
    if (!Number.isFinite(projectId) || tab !== "execute") return;
    api
      .projectVersionHistory(projectId)
      .then((result) => setVersionHistory(result.version_history ?? []))
      .catch((e) => {
        setVersionHistory([]);
        setPollErr(`Version history unavailable: ${String((e as Error).message ?? e)}`);
      });
  }, [projectId, tab, runs.length, tasks.length]);

  useEffect(() => {
    if (tab !== "review" || !Number.isFinite(projectId)) return;
    api
      .projectPreviewStatus(projectId)
      .then((status) => applyPreviewStatus(status))
      .catch((e) => setPollErr(`Preview status check failed: ${String((e as Error).message ?? e)}`));
  }, [tab, projectId]);

  useEffect(() => {
    if (!previewPollActive || tab !== "review" || !Number.isFinite(projectId)) return;
    let cancelled = false;
    let attempts = 0;

    const tick = async () => {
      attempts += 1;
      const status = await api.projectPreviewStatus(projectId);
      if (cancelled) return true;
      applyPreviewStatus(status);
      return Boolean(status.reachable || status.phase === "ready");
    };

    const run = async () => {
      while (!cancelled && attempts < 40) {
        try {
          const done = await tick();
          if (done) return;
        } catch {
          if (!cancelled) {
            setPreviewRuntime((prev) => ({
              ...prev,
              message: "Could not reach preview status endpoint.",
            }));
          }
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
      }
      if (!cancelled) {
        setPreviewRuntime((prev) => ({
          ...prev,
          phase: prev.phase === "starting" ? "launched" : prev.phase,
          message:
            prev.message ??
            "Dev server may still be starting. Use Open app below when your terminal shows it is ready.",
        }));
        setPreviewPollActive(false);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [previewPollActive, tab, projectId]);

  const activeRunForPoll = runs.find((run) => ["RUNNING", "PENDING", "STARTED"].includes(String(run.status ?? "").toUpperCase()));

  useEffect(() => {
    if (!Number.isFinite(projectId)) return;
    const shouldPoll = tab === "execute" || tab === "review" || Boolean(activeRunForPoll);
    if (!shouldPoll) return;
    const intervalMs = activeRunForPoll ? 3_000 : 10_000;
    const interval = window.setInterval(() => {
      load().catch((e) => setPollErr(`Background refresh failed: ${String((e as Error).message ?? e)}`));
    }, intervalMs);
    return () => window.clearInterval(interval);
  }, [projectId, tab, activeRunForPoll?.agent_run_id]);

  const visibleTasks = useMemo(
    () => tasks.filter((task) => String(task.status ?? "").toUpperCase() !== "SUPERSEDED"),
    [tasks],
  );
  const hasContext = documents.length > 0;
  const hasPlan = visibleTasks.length > 0 || Boolean(analysisResult);
  const activeRun = runs.find((run) => ["RUNNING", "PENDING", "STARTED"].includes(String(run.status ?? "").toUpperCase()));
  const tasksAwaitingRun =
    visibleTasks.length > 0 &&
    visibleTasks.every((task) =>
      ["QUEUED", "PENDING", "READY_FOR_AGENT", "PLANNED"].includes(String(task.status ?? "").toUpperCase()),
    );
  const boardRun = resolveBoardRun(runs, tasksAwaitingRun);
  const boardRunId = Number(boardRun?.agent_run_id ?? 0);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !Number.isFinite(boardRunId) || boardRunId <= 0) {
      setBoardRunEvents([]);
      return;
    }
    api
      .projectRunEvents(projectId, boardRunId, 2000)
      .then(setBoardRunEvents)
      .catch((e) => {
        setBoardRunEvents([]);
        setPollErr(`Run events unavailable: ${String((e as Error).message ?? e)}`);
      });
  }, [projectId, boardRunId]);

  const boardTasks = useMemo(() => {
    if (!boardRunId || boardRunEvents.length === 0) return visibleTasks;
    return visibleTasks.map((task) => {
      const taskId = Number(task.task_id);
      if (!Number.isFinite(taskId)) return task;
      return {
        ...task,
        status: taskStatusFromRunEvents(taskId, boardRunEvents, String(task.status ?? "")),
      };
    });
  }, [visibleTasks, boardRunId, boardRunEvents]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !activeRun || boardRunId <= 0 || boardRunEvents.length === 0) return;
    const runStatus = String(activeRun.status ?? "").toUpperCase();
    if (runStatus !== "RUNNING") return;
    const allCompleted =
      boardTasks.length > 0 &&
      boardTasks.every((task) => ["COMPLETED", "DONE", "PASSED"].includes(String(task.status ?? "").toUpperCase()));
    if (!allCompleted) return;
    api
      .reconcileProjectRun(projectId, boardRunId)
      .then(() => load())
      .catch((e) => setPollErr(`Run reconcile failed: ${String((e as Error).message ?? e)}`));
  }, [projectId, activeRun, boardRunId, boardRunEvents.length, boardTasks]);
  const boardProgress = boardTasks.length
    ? Math.round(boardTasks.reduce((sum, task) => sum + taskProgress(task.status), 0) / boardTasks.length)
    : 0;

  const executionMode = String(
    (metadata?.runtime_preferences as Record<string, unknown> | undefined)?.execution_mode ?? "standard",
  );
  const milestonePreviewUrl = String(
    asRecord((metadata?.runtime_preferences as Record<string, unknown> | undefined)?.preview_session).preview_url ?? "",
  );

  const milestoneEventCount = useMemo(
    () =>
      boardRunEvents.filter((event) =>
        ["MILESTONE_COMPLETED", "PROGRESS_UPDATE", "TASK_COMPLETED", "TASK_FAILED"].includes(
          String(event.event_type ?? "").toUpperCase(),
        ),
      ).length,
    [boardRunEvents],
  );

  const refreshProgress = useCallback(() => {
    if (!Number.isFinite(projectId) || executionMode !== "milestones") {
      setProgress(null);
      return;
    }
    api
      .projectProgress(projectId)
      .then(setProgress)
      .catch((e) => setPollErr(`Progress unavailable: ${String((e as Error).message ?? e)}`));
  }, [projectId, executionMode]);

  useEffect(() => {
    refreshProgress();
  }, [refreshProgress, milestoneEventCount]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || executionMode !== "milestones" || !activeRunForPoll) return;
    const interval = window.setInterval(refreshProgress, 5_000);
    return () => window.clearInterval(interval);
  }, [projectId, executionMode, activeRunForPoll?.agent_run_id, refreshProgress]);

  const promoteToMain = useCallback(async () => {
    if (!Number.isFinite(projectId)) return;
    setPromotingToMain(true);
    setErr(null);
    try {
      await api.promoteProjectToMain(projectId);
      setMessage("Promoted mas/preview to main.");
      await load();
    } catch (e) {
      setErr(`Promote to main failed: ${String((e as Error).message ?? e)}`);
    } finally {
      setPromotingToMain(false);
    }
  }, [projectId]);

  const swimlanes = useMemo(
    () => [
      {
        key: "todo",
        title: "To do",
        tasks: boardTasks.filter((task) =>
          ["", "READY_FOR_AGENT", "QUEUED", "PENDING", "PLANNED"].includes(String(task.status ?? "").toUpperCase()),
        ),
      },
      {
        key: "doing",
        title: "In progress",
        tasks: boardTasks.filter((task) =>
          ["RUNNING", "STARTED", "IN_PROGRESS", "PROCESSING"].includes(String(task.status ?? "").toUpperCase()),
        ),
      },
      {
        key: "done",
        title: "Done",
        tasks: boardTasks.filter((task) => ["COMPLETED", "DONE", "PASSED"].includes(String(task.status ?? "").toUpperCase())),
      },
      {
        key: "attention",
        title: "Needs attention",
        tasks: boardTasks.filter((task) =>
          ["FAILED", "ERROR", "CANCELLED", "BLOCKED"].includes(String(task.status ?? "").toUpperCase()),
        ),
      },
    ],
    [boardTasks],
  );

  const projectReadyForPreview = useMemo(() => {
    if (!repoPath.trim()) return false;
    const runComplete = runs.some((run) => String(run.status ?? "").toUpperCase() === "COMPLETED");
    const tasksComplete =
      boardTasks.length > 0 &&
      boardTasks.every((task) => ["COMPLETED", "DONE", "PASSED"].includes(String(task.status ?? "").toUpperCase()));
    return runComplete || tasksComplete;
  }, [repoPath, runs, boardTasks]);

  const launchPreview = useCallback(
    async (options?: { auto?: boolean }) => {
      if (!Number.isFinite(projectId) || previewLaunching) return;
      setPreviewLaunching(true);
      setErr(null);
      setMessage(null);
      setPreviewActivity([]);
      setPreviewSteps([
        { id: "workspace", label: "Resolve workspace", status: "active", detail: repoPath || "…" },
        { id: "detect", label: "Detect app entrypoint", status: "pending" },
        { id: "port", label: "Allocate available port", status: "pending" },
        { id: "spawn", label: "Start dev server", status: "pending" },
        { id: "health", label: "Wait for app to respond", status: "pending" },
      ]);
      appendPreviewActivity(
        options?.auto ? "Project loaded — starting preview automatically…" : "Launch preview requested…",
      );
      setPreviewRuntime({
        phase: "starting",
        previewUrl: "",
        openUrl: "",
        message: "Preparing to launch your application…",
      });
      setPreviewPollActive(true);

      try {
        appendPreviewActivity("Scanning workspace for package.json and dev scripts…");
        const detected = await api.detectProjectPreview(projectId);
        setPreviewSteps((steps) =>
          steps.map((step) =>
            step.id === "workspace"
              ? { ...step, status: "done", detail: detected.repo_path ?? repoPath }
              : step.id === "detect"
                ? {
                    ...step,
                    status: detected.ok ? "done" : "error",
                    detail: detected.ok
                      ? `${detected.preview_command ?? ""} (${detected.detected_from ?? "detected"})`
                      : detected.error,
                  }
                : step,
          ),
        );
        if (!detected.ok) {
          throw new Error(detected.error ?? "Could not detect how to run this app.");
        }
        const url = String(detected.preview_url ?? "");
        if (!url || url.includes(":5173")) {
          throw new Error("Preview would conflict with the dashboard on port 5173. Retry after backend restart.");
        }
        setPreviewUrl(url);
        setPreviewSummary(
          `${detected.preview_command ?? ""} → ${url}${detected.port_note ? ` — ${detected.port_note}` : ""}`,
        );
        appendPreviewActivity(detected.port_note ?? `Using preview URL ${url}`);
        setPreviewSteps((steps) =>
          steps.map((step) =>
            step.id === "port"
              ? {
                  ...step,
                  status: "done",
                  detail: detected.port_note ?? `Port ${detected.allocated_port ?? ""}`,
                }
              : step,
          ),
        );

        appendPreviewActivity(`Running: ${detected.preview_command ?? "dev server"}`);
        setPreviewSteps((steps) =>
          steps.map((step) => (step.id === "spawn" ? { ...step, status: "active" } : step)),
        );
        const preview = await api.startProjectPreview(projectId);
        if (preview.steps?.length) {
          setPreviewSteps(
            preview.steps.map((step) => ({
              id: step.id,
              label: step.label,
              status: (step.status as PreviewStep["status"]) || "done",
              detail: step.detail,
            })),
          );
        }
        const openUrl = String(preview.open_url ?? preview.preview_url ?? url);
        if (!preview.ok) {
          throw new Error(preview.error ?? "Could not start preview.");
        }
        appendPreviewActivity(preview.message ?? "Dev server process started.");
        const phase: PreviewPhase =
          preview.phase === "ready" || preview.reachable ? "ready" : "launched";
        setPreviewRuntime({
          phase,
          previewUrl: String(preview.preview_url ?? openUrl),
          openUrl,
          command: preview.command,
          message: preview.message ?? `App starting at ${openUrl}`,
          reachable: preview.reachable,
          statusCode: preview.status_code,
        });
        setPreviewUrl(openUrl);
        if (phase !== "ready") {
          appendPreviewActivity("Waiting for the dev server to accept connections…");
          setPreviewPollActive(true);
        } else {
          appendPreviewActivity("App is responding — opening in your browser.");
          setPreviewPollActive(false);
        }
        setMessage(preview.message ?? `Preview running at ${openUrl}`);
      } catch (ex: unknown) {
        const detail = ex instanceof Error ? ex.message : String(ex);
        appendPreviewActivity(`Error: ${detail}`);
        setPreviewRuntime({
          phase: "failed",
          previewUrl: previewUrl,
          openUrl: previewUrl,
          message: detail,
        });
        setPreviewPollActive(false);
        setErr(detail);
      } finally {
        setPreviewLaunching(false);
      }
    },
    [projectId, previewLaunching, repoPath, previewUrl, appendPreviewActivity],
  );

  useEffect(() => {
    if (!project || !projectReadyForPreview || autoPreviewOnce.current || previewLaunching) return;
    if (previewRuntime.phase === "ready" || previewRuntime.phase === "starting") return;
    autoPreviewOnce.current = true;
    goToTab("review");
    const timer = window.setTimeout(() => {
      void launchPreview({ auto: true });
    }, 600);
    return () => window.clearTimeout(timer);
  }, [project, projectReadyForPreview, previewLaunching, previewRuntime.phase, launchPreview]);

  const previewOpenedRef = useRef(false);
  useEffect(() => {
    if (
      previewRuntime.phase === "ready" &&
      previewRuntime.openUrl &&
      previewRuntime.openUrl !== "pending" &&
      !previewOpenedRef.current
    ) {
      previewOpenedRef.current = true;
      window.open(previewRuntime.openUrl, "_blank", "noopener,noreferrer");
    }
  }, [previewRuntime.phase, previewRuntime.openUrl]);

  const bannerItems = useMemo(() => {
    const items: StatusBannerItem[] = [];
    if (err) items.push({ id: "load", message: err, severity: "error" });
    if (pollErr) items.push({ id: "poll", message: pollErr, severity: "warning" });
    if (healthErr) {
      items.push({
        id: "health",
        message: healthErr,
        severity: "warning",
        hint: "Check API on port 8001 and database connectivity.",
      });
    }
    return items;
  }, [err, pollErr, healthErr]);

  if (!Number.isFinite(projectId)) return <p className="text-sm text-neutral-600">Invalid project.</p>;
  if (!project) {
    if (err) {
      return (
        <div className="space-y-3 rounded-lg border border-neutral-300 bg-paper-field p-4">
          <StatusBanner items={bannerItems} />
          <p className="text-sm text-neutral-800">Could not load project.</p>
          <p className="text-sm text-red-700">{err}</p>
          <button
            type="button"
            className="rounded-md border border-neutral-400 bg-white px-3 py-1.5 text-sm hover:bg-neutral-50"
            onClick={() => void load()}
          >
            Retry
          </button>
        </div>
      );
    }
    if (loadingProject) return <p className="text-sm text-neutral-600">Loading project...</p>;
    return <p className="text-sm text-neutral-600">Project not found.</p>;
  }

  const saveRuntimeSettings = async () => {
    const runtimePreferences = metadata?.runtime_preferences ?? {};
    const nextRuntimePreferences = { ...runtimePreferences };
    if (repoPath.trim()) {
      nextRuntimePreferences.repo_path = repoPath.trim();
      delete nextRuntimePreferences.workspace_parent_path;
    } else if (workspaceParentPath.trim()) {
      nextRuntimePreferences.workspace_parent_path = workspaceParentPath.trim();
      delete nextRuntimePreferences.repo_path;
    } else {
      delete nextRuntimePreferences.repo_path;
      delete nextRuntimePreferences.workspace_parent_path;
    }
    nextRuntimePreferences.provider = cliRuntime;
    nextRuntimePreferences.runtime = cliRuntime;
    nextRuntimePreferences.reviewer_provider = reviewerProvider;
    nextRuntimePreferences.model_selection_mode = modelSelectionMode;
    if (modelSelectionMode === "fixed") {
      nextRuntimePreferences.fixed_model = fixedModel;
    } else {
      delete nextRuntimePreferences.fixed_model;
    }
    const nextMetadata = await api.updateProjectMetadata(projectId, {
      repository_url: metadata?.repository_url ?? undefined,
      default_branch: metadata?.default_branch ?? "main",
      runtime_preferences: nextRuntimePreferences,
      metadata: {
        ...(metadata?.metadata ?? {}),
        analysis_goal:
          goal.trim() ||
          textValue(metadata?.metadata?.analysis_goal, `Build ${project.project_name} from serialized project context.`),
      },
      updated_by: "dashboard-flow",
    });
    setMetadata(nextMetadata);
    return nextMetadata;
  };

  const uploadDocuments = async () => {
    if (uploadFiles.length === 0) return;
    setWorking("Uploading context");
    setErr(null);
    try {
      const count = uploadFiles.length;
      for (const file of uploadFiles) {
        await api.uploadDocument(projectId, file, uploadNotes);
      }
      setUploadFiles([]);
      setUploadNotes("");
      setMessage(`Uploaded ${count} context file(s).`);
      await load();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  const addTextDocument = async () => {
    if (!docName.trim()) return;
    setWorking("Adding context");
    setErr(null);
    try {
      await api.createDocument(projectId, {
        document_name: docName.trim(),
        raw_text_content: docText,
        file_extension: ".md",
      });
      setDocName("");
      setDocText("");
      setMessage("Text context added.");
      await load();
      goToTab("serialize");
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  const importFigmaDesign = async () => {
    if (!figmaUrl.trim()) return;
    if (!figmaApiToken.trim()) {
      setErr("Add a Figma personal access token in Settings (sidebar) first.");
      return;
    }
    setWorking("Importing Figma design");
    setErr(null);
    try {
      const result = await api.importFigmaDesign(projectId, {
        url: figmaUrl.trim(),
        notes: figmaNotes.trim() || undefined,
        token: figmaApiToken.trim(),
      });
      setLastFigmaImport(result);
      setFigmaUrl("");
      setFigmaNotes("");
      const secCount = result.sections?.length ?? 0;
      const assetCount = result.asset_document_ids?.length ?? 0;
      setMessage(
        `Imported Figma v${result.extraction_version ?? "2"}: ${result.document_name} — ${secCount} sections, ${assetCount} assets.`,
      );
      await load();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  const importDesignPack = async () => {
    if (!designPackFile) return;
    setWorking("Importing design pack");
    setErr(null);
    try {
      const result = await api.importDesignPack(
        projectId,
        designPackFile,
        designPackNotes.trim() || undefined,
      );
      setLastFigmaImport(result);
      setDesignPackFile(null);
      setDesignPackNotes("");
      setDesignPackInputKey((key) => key + 1);
      const secCount = result.sections?.length ?? 0;
      const assetCount = result.asset_document_ids?.length ?? 0;
      setMessage(
        `Imported design pack (${result.extraction_version ?? "plugin-v1"}): ${result.document_name} — ${secCount} sections, ${assetCount} assets.`,
      );
      await load();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  const serializeProject = async () => {
    setErr(null);
    setMessage(null);
    try {
      const inferredGoal =
        goal.trim() ||
        `Serialize the uploaded context for ${project.project_name} into purpose, scope, and executable tasks.`;
      await saveRuntimeSettings();

      let effectiveRepoPath = repoPath.trim();
      const parentPath = workspaceParentPath.trim();

      if (parentPath && !effectiveRepoPath) {
        const slug = slugifyProjectName(project.project_name ?? `project-${projectId}`);
        setWorking(`Creating ${slug} folder and initializing git…`);
        const prepared = await api.prepareProjectWorkspace(projectId, {
          mode: "create",
          parent_path: parentPath,
          save_to_project: true,
        });
        effectiveRepoPath = String(prepared.repo_path ?? "").trim();
        if (!effectiveRepoPath) {
          throw new Error("Workspace was not created. Check the parent folder path and try again.");
        }
        setRepoPath(effectiveRepoPath);
        setWorkspaceParentPath("");
      }

      if (effectiveRepoPath) {
        setWorking("Indexing codebase into context library…");
        await api.startCodebaseSerialize(projectId, { repo_path: effectiveRepoPath });
        await waitForCodebaseSerialization(projectId, (message, percent) => {
          setWorking(`Indexing codebase… ${percent > 0 ? `${percent}%` : message}`);
        });
      }

      setWorking("Serializing context and building task board…");
      const result = await api.analyzeProject(projectId, {
        goal: inferredGoal,
        repo_path: effectiveRepoPath || undefined,
      });
      setAnalysisResult(result);
      setMessage(
        effectiveRepoPath
          ? `Serialized with workspace at ${effectiveRepoPath}. Task board is ready.`
          : "Serialized. Task board is ready.",
      );
      await load();
      goToTab("execute");
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  const refreshProjectFromScratch = async () => {
    const confirmed = window.confirm(
      "Refresh this project from scratch?\n\n" +
        "MAS will create a git version tag of the current worktree state, remove agent worktrees/branches and run records, " +
        "reset tasks to Queued, and clear preview session. Uploaded context documents are kept.",
    );
    if (!confirmed) return;
    setWorking("Refreshing project");
    setErr(null);
    try {
      const result = await api.refreshProject(projectId, {
        reason: refreshReason.trim() || "Project refresh for clean re-run",
        created_by: "dashboard-flow",
      });
      autoPreviewOnce.current = false;
      previewOpenedRef.current = false;
      setPreviewPollActive(false);
      setPreviewRuntime({ phase: "idle", previewUrl: "", openUrl: "" });
      setVersionHistory((prev) => [
        ...(result.version_history_entry
          ? [
              {
                version: result.version,
                git_tag: String(result.version_history_entry.git_tag ?? result.snapshot?.tag ?? ""),
                commit_hash: String(result.version_history_entry.commit_hash ?? result.snapshot?.commit_hash ?? ""),
                reason: String(result.version_history_entry.reason ?? refreshReason),
                created_at: String(result.version_history_entry.created_at ?? ""),
              },
            ]
          : []),
        ...prev,
      ]);
      setMessage(
        `Project refreshed (v${result.version}). Git tag: ${String(result.snapshot?.tag ?? "n/a")}. ` +
          `${result.runs_cleaned} run(s) cleaned, ${result.tasks_reset} task(s) reset.`,
      );
      await load();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  const executeProject = async () => {
    if (!hasPlan) {
      setMessage("Serialize the project before execution. The task board needs generated tasks before a run can start.");
      return;
    }
    setWorking("Starting execution");
    setErr(null);
    setMessage(
      repoPath.trim()
        ? "Creating run and opening live monitor..."
        : "Creating a blocked run monitor. Serialize with a workspace path first.",
    );
    try {
      const nextMetadata = await saveRuntimeSettings();
      const reviewedContext = {
        goal:
          goal.trim() ||
          textValue(nextMetadata.metadata?.analysis_goal, `Build ${project.project_name} from serialized project context.`),
        tasks,
        documents: documents.map((doc) => ({
          name: doc.document_name,
          kind: docKind(doc),
          preview: doc.raw_text_preview,
          status: doc.serialization_status,
        })),
        analysis: analysisResult ?? nextMetadata.metadata?.last_analysis_plan ?? null,
      };
      const result = await api.quickRunForProject(projectId, {
        user_prompt: [
          "Execute this Midnight Agent Space project build from the serialized scope.",
          "Use Cursor Agent for code-focused implementation tasks when balanced agent usage is enabled.",
          "Use the configured reviewer CLI (Claude or Codex) for review tasks and the mandatory post-execution design review.",
          "Keep progress observable. Use the project documents as primary context.",
          "Treat Figma links, SVG files, images, and Figma imports as binding visual requirements — match layout, typography, and components.",
          "Before implementation, identify the exact context documents/assets used for each task.",
          "If a design asset cannot be inspected locally, report that gap clearly instead of claiming design adherence.",
          "The reviewer pass must compare the built app at the preview URL against supplied design context and flag mismatches.",
          "",
          JSON.stringify(reviewedContext, null, 2),
        ].join("\n"),
        template_name: "executor_prompt",
        runtime_provider: cliRuntime,
        reviewer_provider: reviewerProvider,
        model_selection_mode: modelSelectionMode,
        model: modelSelectionMode === "fixed" ? fixedModel : undefined,
        execute: true,
        dry_run: false,
        use_worktree: true,
        output_schema_name: "review",
      });
      const runId = result.run?.agent_run_id;
      if (runId) {
        navigate(`/projects/${projectId}/runs/${runId}`);
      } else {
        await load();
        setMessage("Run submitted, but no run id was returned.");
      }
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setWorking(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Link to="/projects" className="text-xs font-bold uppercase tracking-widest text-orange-600">
          Back to projects
        </Link>
        {working && (
          <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-orange-600">
            <Spinner className="h-3.5 w-3.5" />
            {working}
          </span>
        )}
      </div>

      <StatusBanner
        items={bannerItems}
        onDismiss={(id) => {
          if (id === "poll") setPollErr(null);
          if (id === "health") setHealthErr(null);
          if (id === "load") setErr(null);
        }}
      />

      <section className="glass p-6 border-orange-300/80 ring-2 ring-orange-100">
        <p className="heading-sub mb-2">Project execution flow</p>
        <h1 className="heading-main text-2xl">{project.project_name}</h1>
        <div className="mt-5 grid sm:grid-cols-4 gap-2">
          {[
            ["context", "Context", `${documents.length} docs/assets`],
            ["serialize", "Serialize purpose", hasPlan ? "Task plan ready" : "Define scope"],
            ["execute", "Execute board", boardRun ? `Run ${boardRun.agent_run_id}: ${boardRun.status}` : "No active run"],
            ["review", "Review/use", runs.length ? `${runs.length} previous runs` : "No runs yet"],
          ].map(([key, label, detail]) => (
            <button
              key={key}
              type="button"
              onClick={() => goToTab(key as FlowTab)}
              className={`rounded-lg border p-3 text-left ${
                tab === key ? "border-orange-400 bg-orange-50 text-orange-800" : "border-neutral-300 bg-paper-field text-neutral-700"
              }`}
            >
              <p className="text-[10px] font-bold uppercase tracking-widest">{label}</p>
              <p className="text-xs mt-1">{detail}</p>
            </button>
          ))}
        </div>
      </section>

      {message && <div className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-sm text-neutral-700">{message}</div>}

      {tab === "context" && (
        <section className="grid lg:grid-cols-[0.9fr_1.1fr] gap-6">
          <div className="glass p-5 border-neutral-200 space-y-3">
            <p className="heading-sub">Context intake</p>
            {working && <WorkingBanner message={working} />}
            <input
              type="file"
              multiple
              disabled={Boolean(working)}
              className="block w-full text-xs text-neutral-700 file:mr-3 file:rounded-md file:border file:border-neutral-300 file:bg-paper-bright file:px-3 file:py-2 file:text-xs file:font-bold file:uppercase file:tracking-widest file:text-neutral-700 disabled:opacity-50"
              onChange={(e) => setUploadFiles(Array.from(e.target.files ?? []))}
            />
            {uploadFiles.length > 0 && (
              <p className="text-[11px] text-neutral-700">
                {uploadFiles.length} file(s) selected: {uploadFiles.map((f) => f.name).join(", ")}
              </p>
            )}
            <textarea
              className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[90px] text-neutral-900 disabled:opacity-50"
              placeholder="Description / instructions for the selected files (shown in context library)"
              value={uploadNotes}
              disabled={Boolean(working)}
              onChange={(e) => setUploadNotes(e.target.value)}
            />
            <p className="text-[11px] text-neutral-500">Max file size: {uploadMaxMb} MB per file. Images, PDFs, and design assets are supported.</p>
            <LoadingButton
              loading={working === "Uploading context"}
              loadingLabel="Uploading…"
              disabled={uploadFiles.length === 0 || Boolean(working)}
              onClick={uploadDocuments}
              className="w-full px-4 py-2 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500 disabled:opacity-50"
            >
              Upload context
            </LoadingButton>
            <div className="border-t border-neutral-300 pt-3 space-y-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Figma design</p>
              <input
                className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900 disabled:opacity-50"
                placeholder="Figma design URL (with node-id for a specific frame)"
                value={figmaUrl}
                disabled={Boolean(working)}
                onChange={(e) => setFigmaUrl(e.target.value)}
              />
              <textarea
                className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[72px] text-neutral-900 disabled:opacity-50"
                placeholder="Optional context: what to implement, screen name, breakpoints, etc."
                value={figmaNotes}
                disabled={Boolean(working)}
                onChange={(e) => setFigmaNotes(e.target.value)}
              />
              <p className="text-[11px] text-neutral-500">
                {figmaApiToken.trim()
                  ? "Token configured. Imports section specs, assets, tokens, and per-section PNG exports."
                  : "Set your Figma API token in Settings before importing."}
              </p>
              <LoadingButton
                loading={working === "Importing Figma design"}
                loadingLabel="Importing from Figma…"
                disabled={!figmaUrl.trim() || !figmaApiToken.trim() || Boolean(working)}
                onClick={importFigmaDesign}
                className="w-full px-4 py-2 rounded-lg border border-orange-600 text-orange-600 text-xs font-bold uppercase tracking-widest hover:bg-orange-50 disabled:opacity-50"
              >
                Import from Figma API
              </LoadingButton>
              <div className="rounded-lg border border-dashed border-neutral-300 bg-paper-bright p-3 space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">
                  Figma plugin design pack
                </p>
                <p className="text-[11px] text-neutral-600">
                  Upload the <code className="text-[10px]">mas-*.zip</code> downloaded from Plugins → Development →
                  Midnight Agent Space. No API token required.
                </p>
                <input
                  key={`design-pack-${designPackInputKey}`}
                  type="file"
                  accept=".zip,application/zip"
                  disabled={Boolean(working)}
                  className="block w-full text-xs text-neutral-700 file:mr-3 file:rounded-md file:border file:border-neutral-300 file:bg-white file:px-3 file:py-2 file:text-xs file:font-bold file:uppercase file:tracking-widest file:text-neutral-700 disabled:opacity-50"
                  onChange={(e) => setDesignPackFile(e.target.files?.[0] ?? null)}
                />
                {designPackFile && (
                  <p className="text-[11px] text-neutral-700">
                    Selected: <span className="font-mono">{designPackFile.name}</span> (
                    {(designPackFile.size / (1024 * 1024)).toFixed(1)} MB)
                  </p>
                )}
                <textarea
                  className="w-full bg-white border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[60px] text-neutral-900 disabled:opacity-50"
                  placeholder="Optional notes for this design import"
                  value={designPackNotes}
                  disabled={Boolean(working)}
                  onChange={(e) => setDesignPackNotes(e.target.value)}
                />
                <LoadingButton
                  loading={working === "Importing design pack"}
                  loadingLabel="Importing design pack…"
                  disabled={!designPackFile || Boolean(working)}
                  onClick={importDesignPack}
                  className="w-full px-4 py-2 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500 disabled:opacity-50"
                >
                  Import design pack
                </LoadingButton>
              </div>
              <FigmaDesignStatus
                readiness={designReadiness}
                lastImport={lastFigmaImport}
                reimporting={working === "Re-importing Figma"}
                onReimport={
                  figmaApiToken.trim()
                    ? async () => {
                        setWorking("Re-importing Figma");
                        setErr(null);
                        try {
                          const result = await api.reimportFigmaDesign(projectId, {
                            token: figmaApiToken.trim(),
                          });
                          setLastFigmaImport(result);
                          setMessage(`Re-imported Figma: ${result.document_name}`);
                          await load();
                        } catch (ex: unknown) {
                          setErr(ex instanceof Error ? ex.message : String(ex));
                        } finally {
                          setWorking(null);
                        }
                      }
                    : undefined
                }
              />
            </div>
            <div className="border-t border-neutral-300 pt-3 space-y-3">
              <input
                className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900 disabled:opacity-50"
                placeholder="Text context title"
                value={docName}
                disabled={Boolean(working)}
                onChange={(e) => setDocName(e.target.value)}
              />
              <textarea
                className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[120px] text-neutral-900 disabled:opacity-50"
                placeholder="Paste requirements, notes, or implementation direction"
                value={docText}
                disabled={Boolean(working)}
                onChange={(e) => setDocText(e.target.value)}
              />
              <LoadingButton
                loading={working === "Adding context"}
                loadingLabel="Adding…"
                disabled={!docName.trim() || Boolean(working)}
                onClick={addTextDocument}
                className="w-full px-4 py-2 rounded-lg border border-orange-600 text-orange-600 text-xs font-bold uppercase tracking-widest hover:bg-orange-50 disabled:opacity-50"
              >
                Add text context
              </LoadingButton>
            </div>
          </div>

          <ContextLibrary
            projectId={projectId}
            documents={documents}
            onDeleted={load}
            disabled={Boolean(working)}
          />
        </section>
      )}

      {tab === "serialize" && (
        <section className="glass p-5 border-neutral-200 space-y-4">
          <div>
            <p className="heading-sub">Serialize purpose</p>
            <h2 className="text-lg font-bold text-neutral-900 mt-1">Convert context into task execution scope</h2>
          </div>
          <textarea
            className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[130px] text-neutral-900"
            placeholder="Purpose/goal, optional if the documents already explain it"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
          <RepoPathSelector
            repoPath={repoPath}
            workspaceParentPath={workspaceParentPath}
            onRepoPathChange={setRepoPath}
            onWorkspaceParentChange={setWorkspaceParentPath}
            projectName={project.project_name ?? `project-${projectId}`}
          />
          {previewSummary && (
            <p className="text-[11px] text-neutral-600">
              Preview (auto-detected): <span className="font-mono text-neutral-800">{previewSummary}</span>
            </p>
          )}
          {working && <WorkingBanner message={working} />}

          <LoadingButton
            loading={Boolean(working)}
            loadingLabel={working ?? "Working…"}
            disabled={!hasContext || Boolean(working)}
            onClick={serializeProject}
            className="px-5 py-3 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500 disabled:opacity-50"
          >
            Serialize and open task board
          </LoadingButton>
          <p className="text-[11px] text-neutral-500">
            One step: creates the project folder and git repo (if you chose a parent path), indexes the codebase, serializes
            uploaded context, and opens the task board.
          </p>
        </section>
      )}

      {tab === "execute" && (
        <section className="space-y-4">
          {working && <WorkingBanner message={working} />}
          <div className="glass p-5 border-neutral-200 space-y-4">
            <div>
              <p className="heading-sub">Project version history</p>
              <p className="text-sm text-neutral-600 mt-1">
                Each refresh snapshots agent worktrees to a git tag before clearing runs and resetting tasks.
              </p>
              {versionHistory.length > 0 ? (
                <ul className="mt-3 space-y-2 text-xs text-neutral-700">
                  {[...versionHistory].reverse().slice(0, 5).map((entry) => (
                    <li key={entry.version} className="rounded-lg border border-neutral-300 bg-paper-bright px-3 py-2">
                      <span className="font-bold">v{entry.version}</span>
                      {entry.git_tag ? ` · ${entry.git_tag}` : ""}
                      {entry.commit_hash ? ` · ${entry.commit_hash.slice(0, 8)}` : ""}
                      {entry.created_at ? ` · ${new Date(entry.created_at).toLocaleString()}` : ""}
                      {entry.reason ? <span className="block mt-1 text-neutral-600">{entry.reason}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-neutral-500 mt-2">No refresh snapshots yet.</p>
              )}
              <textarea
                className="mt-3 w-full rounded-lg border border-neutral-300 bg-paper-bright px-3 py-2 text-sm min-h-[72px] text-neutral-900"
                value={refreshReason}
                onChange={(e) => setRefreshReason(e.target.value)}
                placeholder="Why are you refreshing? (saved in version history)"
              />
              <LoadingButton
                loading={working === "Refreshing project"}
                loadingLabel="Refreshing…"
                disabled={Boolean(working)}
                onClick={() => void refreshProjectFromScratch()}
                className="mt-2 px-4 py-2 rounded-lg border border-neutral-500 text-neutral-800 text-xs font-bold uppercase tracking-widest hover:border-orange-400 hover:bg-orange-50 disabled:opacity-50"
              >
                Refresh project from scratch
              </LoadingButton>
            </div>
          </div>

          <div className="glass p-5 border-neutral-200">
            <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
              <div>
                <p className="heading-sub">Execute task board</p>
                <h2 className="text-lg font-bold text-neutral-900 mt-1">Swimlane view</h2>
                <p className="text-sm text-neutral-600 mt-1">
                  Latest/current run: {boardRun ? `#${boardRun.agent_run_id} / ${boardRun.status}` : "none"} / Progress{" "}
                  {boardProgress}% / {runtimeLabel(cliRuntime)} / {modelSelectionLabel(modelSelectionMode)}
                </p>
                {!repoPath.trim() && !workspaceParentPath.trim() && (
                  <p className="text-xs text-orange-700 mt-2">
                    No workspace yet. On Serialize, choose a parent folder (created on serialize) or an existing repo before execute.
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {boardRun && (
                  <Link
                    to={`/projects/${projectId}/runs/${boardRun.agent_run_id}`}
                    className="px-4 py-2 rounded-lg border border-neutral-400 text-neutral-700 text-xs font-bold uppercase tracking-widest hover:border-orange-300"
                  >
                    Open live monitor
                  </Link>
                )}
                <LoadingButton
                  loading={working === "Starting execution"}
                  loadingLabel="Starting…"
                  disabled={
                    !hasPlan ||
                    Boolean(working) ||
                    (designReadiness?.required === true && designReadiness.structural_ready === false)
                  }
                  onClick={executeProject}
                  title={
                    designReadiness?.required && !designReadiness.structural_ready
                      ? (designReadiness.gaps ?? []).join("; ")
                      : undefined
                  }
                  className="px-5 py-2 rounded-lg bg-neutral-900 text-white text-xs font-bold uppercase tracking-widest hover:bg-neutral-700 disabled:opacity-50"
                >
                  Execute build and monitor
                </LoadingButton>
              </div>
            </div>
            <div className="mt-4 h-2 rounded-full bg-neutral-200 overflow-hidden">
              <div className="h-full bg-orange-600 transition-all" style={{ width: `${boardProgress}%` }} />
            </div>
            {executionMode === "milestones" && (
              <div className="mt-4">
                <ProgressDashboard
                  progress={progress}
                  previewUrl={milestonePreviewUrl || undefined}
                  onPromote={promoteToMain}
                  promoting={promotingToMain}
                />
              </div>
            )}
          </div>

          <div className="grid xl:grid-cols-4 md:grid-cols-2 gap-3">
            {swimlanes.map((lane) => (
              <div key={lane.key} className="rounded-lg border border-neutral-300 bg-paper-field p-3 min-h-[260px]">
                <div className="flex items-center justify-between gap-2 mb-3">
                  <h3 className="heading-sub">{lane.title}</h3>
                  <span className="rounded-full border border-neutral-300 bg-paper-bright px-2 py-0.5 text-[10px] font-bold text-neutral-600">
                    {lane.tasks.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {lane.tasks.map((task, index) => {
                    const refs = asRecord(asRecord(task.task_data).rag_ready_context).documents;
                    const refCount = Array.isArray(refs) ? refs.length : documents.length;
                    const progress = taskProgress(task.status);
                    const effort = agentEffortFromTask(task);
                    return (
                      <div key={task.task_id ?? `${lane.key}-${index}`} className="rounded-lg border border-neutral-300 bg-paper-bright p-3">
                        <div className="flex items-start justify-between gap-3">
                          <p className="font-bold text-neutral-900 text-sm">{task.task_name || `Task ${index + 1}`}</p>
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${statusClass(task.status)}`}>
                            {task.status ?? "READY"}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${effortBadgeClass(effort.level)}`}
                            title={effort.rationale}
                          >
                            Agent effort {effort.level}
                            {typeof effort.score === "number" ? ` (${effort.score}/5)` : ""}
                          </span>
                        </div>
                        <p className="text-xs text-neutral-600 mt-2 line-clamp-4">
                          {task.description || "Agent task from serialized project context."}
                        </p>
                        <div className="mt-3 h-1.5 rounded-full bg-neutral-200 overflow-hidden">
                          <div className="h-full bg-orange-600 transition-all" style={{ width: `${progress}%` }} />
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-600">
                          <span className="rounded-full border border-orange-200 bg-orange-50 px-2 py-0.5 text-orange-700">
                            {task.task_type || "task"}
                          </span>
                          <span className="rounded-full border border-neutral-300 bg-paper-field px-2 py-0.5">
                            {refCount} refs
                          </span>
                          {boardRun && (
                            <span className="rounded-full border border-neutral-300 bg-paper-field px-2 py-0.5">
                              run #{boardRun.agent_run_id}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {lane.tasks.length === 0 && <p className="text-xs text-neutral-500">No tasks.</p>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === "review" && (
        <section className="grid lg:grid-cols-[1fr_0.8fr] gap-6">
          <div className="glass p-5 border-neutral-200">
            <p className="heading-sub mb-3">Previous runs and what happened</p>
            <div className="space-y-2">
              {runs.map((run) => {
                const payload = asRecord(run.result_payload);
                const errors = Array.isArray(payload.errors) ? payload.errors.join("; ") : textValue(payload.error, "");
                const warnings = Array.isArray(payload.warnings) ? payload.warnings.join("; ") : "";
                return (
                  <Link
                    key={run.agent_run_id}
                    to={`/projects/${projectId}/runs/${run.agent_run_id}`}
                    className="block rounded-lg border border-neutral-300 bg-paper-field p-3 hover:border-orange-300"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-bold text-neutral-900">Run #{run.agent_run_id}</p>
                        <p className="text-xs text-neutral-600 mt-1">
                          {run.runtime_provider ?? "runtime"} / {run.created_at ?? ""}
                        </p>
                        {(errors || warnings) && (
                          <p className="text-xs text-neutral-700 mt-2 line-clamp-2">{errors || warnings}</p>
                        )}
                      </div>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${statusClass(run.status)}`}>
                        {run.status ?? "UNKNOWN"}
                      </span>
                    </div>
                  </Link>
                );
              })}
              {runs.length === 0 && <p className="text-sm text-neutral-600">No runs yet.</p>}
            </div>
          </div>

          <div className="glass p-5 border-neutral-200 space-y-3">
            <p className="heading-sub">Use project</p>
            <h2 className="font-bold text-neutral-900 text-lg">Launch preview</h2>
            <p className="text-sm text-neutral-600">
              Starts the dev server from your workspace <code className="text-xs">package.json</code> (e.g.{" "}
              <code className="text-xs">npm run dev</code>) and opens the app in your browser.
            </p>
            {previewSummary ? (
              <p className="text-[11px] text-neutral-600 font-mono">{previewSummary}</p>
            ) : repoPath.trim() ? (
              <p className="text-[11px] text-neutral-500">Detecting preview from workspace…</p>
            ) : (
              <p className="text-[11px] text-orange-700">Serialize with a workspace path first so we can find the app.</p>
            )}

            {(previewLaunching || previewSteps.length > 0 || previewRuntime.phase !== "idle") && (
              <div className="rounded-lg border border-neutral-300 bg-paper-field px-4 py-3 space-y-3">
                <p className="text-xs font-bold uppercase tracking-widest text-neutral-800">Launch progress</p>
                <ul className="space-y-2">
                  {previewSteps.map((step) => (
                    <li key={step.id} className="flex gap-2 text-sm">
                      <span
                        className={`mt-0.5 h-2 w-2 rounded-full shrink-0 ${
                          step.status === "done"
                            ? "bg-green-600"
                            : step.status === "active"
                              ? "bg-orange-500 animate-pulse"
                              : step.status === "error"
                                ? "bg-neutral-600"
                                : "bg-neutral-300"
                        }`}
                      />
                      <div>
                        <p className="font-medium text-neutral-900">{step.label}</p>
                        {step.detail && <p className="text-[11px] text-neutral-600 break-all">{step.detail}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
                {previewActivity.length > 0 && (
                  <div className="max-h-32 overflow-y-auto rounded border border-neutral-200 bg-paper-bright p-2 space-y-1">
                    {previewActivity.map((line, index) => (
                      <p key={`${line}-${index}`} className="text-[11px] font-mono text-neutral-700">
                        {line}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            {(previewRuntime.phase !== "idle" || previewRuntime.reachable || previewRuntime.openUrl) && (
              <div
                className={`rounded-lg border px-4 py-3 space-y-2 ${
                  previewRuntime.phase === "ready"
                    ? "border-green-300 bg-green-50"
                    : previewRuntime.phase === "failed"
                      ? "border-neutral-400 bg-neutral-100"
                      : "border-orange-200 bg-orange-50"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-bold uppercase tracking-widest text-neutral-800">
                    {previewRuntime.phase === "ready"
                      ? "App is running"
                      : previewRuntime.phase === "starting"
                        ? "Starting preview…"
                        : previewRuntime.phase === "failed"
                          ? "Preview failed"
                          : "Waiting for dev server"}
                  </p>
                  {previewRuntime.phase === "ready" && previewRuntime.statusCode != null && (
                    <span className="text-[10px] font-mono text-green-800">HTTP {previewRuntime.statusCode}</span>
                  )}
                </div>
                {previewRuntime.message && (
                  <p className="text-sm text-neutral-700">{previewRuntime.message}</p>
                )}
                {previewRuntime.command && (
                  <p className="text-[11px] font-mono text-neutral-600 break-all">{previewRuntime.command}</p>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  {previewRuntime.openUrl && previewRuntime.openUrl !== "pending" && (
                    <>
                      <a
                        href={previewRuntime.openUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-widest ${
                          previewRuntime.phase === "ready"
                            ? "bg-green-700 text-white hover:bg-green-600"
                            : "bg-orange-600 text-white hover:bg-orange-500"
                        }`}
                      >
                        {previewRuntime.phase === "ready" ? "Open app" : "Open app (may still be starting)"}
                      </a>
                      <a
                        href={previewRuntime.openUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-4 py-2 rounded-lg border border-neutral-400 text-neutral-700 text-xs font-bold uppercase tracking-widest hover:border-orange-300"
                      >
                        Open in new tab
                      </a>
                    </>
                  )}
                  <button
                    type="button"
                    className="px-3 py-2 rounded-lg border border-neutral-300 text-[10px] font-bold uppercase tracking-widest text-neutral-600 hover:border-orange-300"
                    onClick={() => {
                      void navigator.clipboard?.writeText(previewRuntime.openUrl);
                      setMessage(`Copied preview URL: ${previewRuntime.openUrl}`);
                    }}
                  >
                    Copy URL
                  </button>
                </div>
                <p className="text-[11px] text-neutral-600 break-all">
                  <span className="font-bold">URL:</span> {previewRuntime.openUrl}
                </p>
              </div>
            )}

            <button
              type="button"
              disabled={previewLaunching || !repoPath.trim()}
              className="w-full px-5 py-3 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500 disabled:opacity-60 flex items-center justify-center gap-2"
              onClick={() => {
                previewOpenedRef.current = false;
                void launchPreview();
              }}
            >
              {previewLaunching && (
                <span
                  className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin"
                  aria-hidden
                />
              )}
              {previewLaunching
                ? "Launching your app…"
                : previewRuntime.phase === "ready"
                  ? "Restart preview"
                  : "Run app and open preview"}
            </button>
            {projectReadyForPreview && !previewLaunching && previewRuntime.phase === "idle" && (
              <p className="text-[11px] text-neutral-500">
                Preview will start automatically when this page finishes loading.
              </p>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
