import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  type AgentRun,
  type DocumentVersion,
  type Project,
  type ProjectDocument,
  type ProjectSummary,
} from "../api";

type Tab = "overview" | "documents" | "runs" | "tasks" | "history" | "settings";

export default function ProjectDetail() {
  const { id } = useParams();
  const projectId = Number(id);
  const [tab, setTab] = useState<Tab>("overview");
  const [project, setProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [docs, setDocs] = useState<ProjectDocument[]>([]);
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);
  const [runtimeInfo, setRuntimeInfo] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ project_name: "", description: "", status: "", project_type: "" });
  const [metadataForm, setMetadataForm] = useState({
    repository_url: "",
    default_branch: "main",
    runtime_preferences_json: "{}",
  });

  const [docDraft, setDocDraft] = useState({
    document_name: "",
    raw_text_content: "",
    file_extension: ".md",
  });
  const [selectedDoc, setSelectedDoc] = useState<ProjectDocument | null>(null);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<DocumentVersion | null>(null);

  const [runForm, setRunForm] = useState({
    user_prompt: "",
    template_name: "quick_run_system_prompt",
    runtime_provider: "codex-cli",
    execute: false,
    use_worktree: true,
    output_schema_name: "",
  });
  const [runMsg, setRunMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(projectId)) return;
    setErr(null);
    api
      .project(projectId)
      .then((p) => {
        setProject(p);
        setForm({
          project_name: p.project_name ?? "",
          description: p.description ?? "",
          status: p.status ?? "",
          project_type: p.project_type ?? "",
        });
      })
      .catch((e) => setErr(e.message));
    api
      .projectSummary(projectId)
      .then(setSummary)
      .catch(() => setSummary(null));
    api
      .projectMetadata(projectId)
      .then((meta) =>
        setMetadataForm({
          repository_url: meta.repository_url ?? "",
          default_branch: meta.default_branch ?? "main",
          runtime_preferences_json: JSON.stringify(meta.runtime_preferences ?? {}, null, 2),
        }),
      )
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    if (!Number.isFinite(projectId)) return;
    if (tab === "documents") {
      api.documents(projectId).then(setDocs).catch((e) => setErr(e.message));
      return;
    }
    if (tab === "tasks") {
      api.tasks(projectId).then(setTasks).catch((e) => setErr(e.message));
      return;
    }
    if (tab === "runs") {
      api.projectRuns(projectId, 120).then(setRuns).catch((e) => setErr(e.message));
      return;
    }
    if (tab === "history") {
      api.changeHistory(projectId, 250).then(setHistory).catch((e) => setErr(e.message));
      return;
    }
    if (tab === "settings") {
      api.settingsRuntimes().then(setRuntimeInfo).catch(() => setRuntimeInfo(null));
    }
  }, [projectId, tab]);

  if (!Number.isFinite(projectId)) {
    return <p className="text-neutral-600">Invalid project</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 text-sm text-neutral-600">
        <Link to="/projects" className="hover:text-orange-600 font-bold uppercase tracking-widest text-xs">
          ← Projects
        </Link>
      </div>

      {err && <div className="text-neutral-700 text-sm">{err}</div>}

      {!project ? (
        <p className="text-neutral-600">Loading…</p>
      ) : (
        <>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <p className="heading-sub mb-1">Project</p>
              <h1 className="heading-main text-xl sm:text-2xl">{project.project_name}</h1>
            </div>
            <div className="flex rounded-lg border border-neutral-300 overflow-hidden text-xs font-bold uppercase tracking-widest bg-paper-lift/55">
              {(["overview", "documents", "runs", "tasks", "history", "settings"] as Tab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`px-4 py-2 capitalize ${
                    tab === t ? "bg-orange-600 text-white" : "text-neutral-600 hover:bg-neutral-100"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {tab === "overview" && (
            <div className="grid lg:grid-cols-2 gap-6">
              <div className="glass p-6 space-y-3">
                <h2 className="heading-sub">Project summary</h2>
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-paper-field rounded-lg border border-neutral-300 p-3">
                    <p className="heading-sub">Documents</p>
                    <p className="stat-number text-xl">{summary?.counts.documents ?? 0}</p>
                  </div>
                  <div className="bg-paper-field rounded-lg border border-neutral-300 p-3">
                    <p className="heading-sub">Tasks</p>
                    <p className="stat-number text-xl">{summary?.counts.tasks ?? 0}</p>
                  </div>
                  <div className="bg-paper-field rounded-lg border border-neutral-300 p-3">
                    <p className="heading-sub">Runs</p>
                    <p className="stat-number text-xl">{summary?.counts.runs ?? 0}</p>
                  </div>
                </div>
                <p className="text-sm text-neutral-600">
                  Latest run:{" "}
                  {summary?.latest_run ? (
                    <>
                      #{summary.latest_run.agent_run_id} · {summary.latest_run.status}
                    </>
                  ) : (
                    "—"
                  )}
                </p>
              </div>

              <form
                className="glass p-6 space-y-4"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setSaving(true);
                  setErr(null);
                  try {
                    const updated = await api.patchProject(projectId, {
                      project_name: form.project_name || undefined,
                      description: form.description || undefined,
                      status: form.status || undefined,
                      project_type: form.project_type || undefined,
                    });
                    setProject(updated);
                    const nextSummary = await api.projectSummary(projectId);
                    setSummary(nextSummary);
                  } catch (ex: unknown) {
                    setErr(ex instanceof Error ? ex.message : String(ex));
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                <h2 className="heading-sub mb-2">Project details</h2>
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">Name</label>
                <input
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                  value={form.project_name}
                  onChange={(e) => setForm((f) => ({ ...f, project_name: e.target.value }))}
                />
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">Type</label>
                <input
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                  value={form.project_type}
                  onChange={(e) => setForm((f) => ({ ...f, project_type: e.target.value }))}
                />
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">Status</label>
                <input
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                  value={form.status}
                  onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
                />
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">Description</label>
                <textarea
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[100px] text-neutral-900"
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                />
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white"
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                  {String(project.status ?? "").toUpperCase() !== "ARCHIVED" && (
                    <button
                      type="button"
                      className="px-4 py-2 rounded-lg border border-neutral-400 text-neutral-700 text-sm font-bold uppercase tracking-widest"
                      onClick={async () => {
                        await api.archiveProject(projectId);
                        const next = await api.project(projectId);
                        setProject(next);
                        setForm((f) => ({ ...f, status: next.status ?? "ARCHIVED" }));
                      }}
                    >
                      Archive
                    </button>
                  )}
                </div>
              </form>
            </div>
          )}

          {tab === "documents" && (
            <div className="space-y-6">
              <div className="glass p-4 border-neutral-200">
                <h2 className="heading-sub mb-3">Create document</h2>
                <div className="grid sm:grid-cols-3 gap-2">
                  <input
                    className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                    placeholder="Document name"
                    value={docDraft.document_name}
                    onChange={(e) => setDocDraft((d) => ({ ...d, document_name: e.target.value }))}
                  />
                  <input
                    className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                    placeholder="Extension"
                    value={docDraft.file_extension}
                    onChange={(e) => setDocDraft((d) => ({ ...d, file_extension: e.target.value }))}
                  />
                  <button
                    type="button"
                    className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white"
                    onClick={async () => {
                      if (!docDraft.document_name.trim()) return;
                      await api.createDocument(projectId, {
                        document_name: docDraft.document_name.trim(),
                        raw_text_content: docDraft.raw_text_content,
                        file_extension: docDraft.file_extension,
                      });
                      setDocDraft((d) => ({ ...d, document_name: "" }));
                      const d = await api.documents(projectId);
                      setDocs(d);
                    }}
                  >
                    Create
                  </button>
                </div>
                <textarea
                  className="mt-2 w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[90px] text-neutral-900"
                  placeholder="Initial content..."
                  value={docDraft.raw_text_content}
                  onChange={(e) => setDocDraft((d) => ({ ...d, raw_text_content: e.target.value }))}
                />
              </div>

              <div className="grid lg:grid-cols-3 gap-4">
                <div className="glass p-4 border-neutral-200">
                  <h2 className="heading-sub mb-2">Documents</h2>
                  <ul className="space-y-2 text-sm">
                    {docs.map((d) => (
                      <li key={d.document_id}>
                        <button
                          type="button"
                          className={`w-full text-left rounded border px-3 py-2 ${
                            selectedDoc?.document_id === d.document_id
                              ? "border-orange-400 bg-orange-50"
                              : "border-neutral-300 hover:border-orange-300"
                          }`}
                          onClick={async () => {
                            const full = await api.document(projectId, d.document_id);
                            setSelectedDoc(full);
                            const v = await api.documentVersionsV2(projectId, d.document_id, 100);
                            setVersions(v);
                            setSelectedVersion(v[0] ?? null);
                          }}
                        >
                          <p className="text-neutral-800">{d.document_name}</p>
                          <p className="text-xs text-neutral-600">{d.serialization_status ?? "PENDING"}</p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="glass p-4 border-neutral-200 lg:col-span-2 space-y-3">
                  {!selectedDoc ? (
                    <p className="text-sm text-neutral-600">Select a document to view/edit content and versions.</p>
                  ) : (
                    <>
                      <div className="flex items-center justify-between gap-2">
                        <h2 className="heading-sub">Document editor</h2>
                        <button
                          type="button"
                          className="text-xs font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500"
                          onClick={async () => {
                            if (!selectedDoc) return;
                            await api.patchDocument(projectId, selectedDoc.document_id, {
                              raw_text_content: selectedDoc.raw_text_content ?? "",
                              create_new_version: true,
                              change_summary: "Edited in dashboard",
                              source: "dashboard-editor",
                            });
                            const v = await api.documentVersionsV2(projectId, selectedDoc.document_id, 100);
                            setVersions(v);
                            setSelectedVersion(v[0] ?? null);
                          }}
                        >
                          Save as new version
                        </button>
                      </div>
                      <input
                        className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                        value={selectedDoc.document_name}
                        onChange={(e) =>
                          setSelectedDoc((prev) => (prev ? { ...prev, document_name: e.target.value } : prev))
                        }
                      />
                      <textarea
                        className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[180px] text-neutral-900 font-mono"
                        value={selectedDoc.raw_text_content ?? ""}
                        onChange={(e) =>
                          setSelectedDoc((prev) => (prev ? { ...prev, raw_text_content: e.target.value } : prev))
                        }
                      />

                      <div>
                        <h3 className="heading-sub mb-2">Versions</h3>
                        <div className="max-h-48 overflow-y-auto border border-neutral-300 rounded-lg divide-y divide-neutral-200">
                          {versions.map((v) => (
                            <button
                              key={v.document_version_id}
                              type="button"
                              className={`w-full text-left px-3 py-2 text-sm ${
                                selectedVersion?.document_version_id === v.document_version_id
                                  ? "bg-orange-50"
                                  : "hover:bg-paper-field"
                              }`}
                              onClick={async () => {
                                const full = await api.documentVersionV2(
                                  projectId,
                                  selectedDoc.document_id,
                                  v.version_number,
                                );
                                setSelectedVersion(full);
                              }}
                            >
                              v{v.version_number} · {v.version_label || "no label"} · {v.source || "manual"}
                            </button>
                          ))}
                        </div>
                        {selectedVersion && (
                          <pre className="mt-2 text-xs text-neutral-700 whitespace-pre-wrap break-words bg-paper-field rounded-lg border border-neutral-300 p-3 max-h-56 overflow-y-auto">
                            {selectedVersion.raw_text_content || selectedVersion.change_summary || "No stored content"}
                          </pre>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === "runs" && (
            <div className="space-y-4">
              <div className="glass p-6 border-neutral-200 space-y-3">
                <h2 className="heading-sub">Quick run</h2>
                <textarea
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm min-h-[120px] text-neutral-900"
                  placeholder="Describe what the agent should change..."
                  value={runForm.user_prompt}
                  onChange={(e) => setRunForm((r) => ({ ...r, user_prompt: e.target.value }))}
                />
                <div className="grid sm:grid-cols-4 gap-2">
                  <input
                    className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-xs text-neutral-900"
                    value={runForm.template_name}
                    onChange={(e) => setRunForm((r) => ({ ...r, template_name: e.target.value }))}
                    placeholder="Template"
                  />
                  <input
                    className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-xs text-neutral-900"
                    value={runForm.runtime_provider}
                    onChange={(e) => setRunForm((r) => ({ ...r, runtime_provider: e.target.value }))}
                    placeholder="Runtime"
                  />
                  <input
                    className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-xs text-neutral-900"
                    value={runForm.output_schema_name}
                    onChange={(e) => setRunForm((r) => ({ ...r, output_schema_name: e.target.value }))}
                    placeholder="Output schema (optional)"
                  />
                  <label className="flex items-center gap-2 text-xs text-neutral-600 border border-neutral-300 rounded-lg px-3">
                    <input
                      type="checkbox"
                      checked={runForm.execute}
                      onChange={(e) => setRunForm((r) => ({ ...r, execute: e.target.checked }))}
                    />
                    Execute now
                  </label>
                </div>
                <label className="flex items-center gap-2 text-xs text-neutral-600">
                  <input
                    type="checkbox"
                    checked={runForm.use_worktree}
                    onChange={(e) => setRunForm((r) => ({ ...r, use_worktree: e.target.checked }))}
                  />
                  Use git worktree
                </label>
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white"
                  onClick={async () => {
                    if (!runForm.user_prompt.trim()) return;
                    setRunMsg(null);
                    try {
                      const result = await api.quickRunForProject(projectId, {
                        user_prompt: runForm.user_prompt,
                        template_name: runForm.template_name,
                        runtime_provider: runForm.runtime_provider,
                        execute: runForm.execute,
                        use_worktree: runForm.use_worktree,
                        output_schema_name: runForm.output_schema_name || undefined,
                      });
                      setRunMsg(
                        `Run #${result.run?.agent_run_id ?? "?"} ${runForm.execute ? "started" : "planned"} (${result.run?.status ?? "UNKNOWN"})`,
                      );
                      const nextRuns = await api.projectRuns(projectId, 120);
                      setRuns(nextRuns);
                    } catch (ex: unknown) {
                      setRunMsg(ex instanceof Error ? ex.message : String(ex));
                    }
                  }}
                >
                  Submit run
                </button>
                {runMsg && <p className="text-xs text-neutral-600 break-all">{runMsg}</p>}
              </div>

              <div className="glass overflow-hidden border-neutral-200">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-100 text-left text-[10px] font-bold text-neutral-600 uppercase tracking-widest">
                    <tr>
                      <th className="p-3">Run</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Provider</th>
                      <th className="p-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.agent_run_id} className="border-t border-neutral-200">
                        <td className="p-3 text-neutral-700">#{r.agent_run_id}</td>
                        <td className="p-3 text-neutral-600 uppercase tracking-wide text-xs">{r.status}</td>
                        <td className="p-3 text-neutral-600">{r.runtime_provider}</td>
                        <td className="p-3 text-right space-x-2">
                          <Link
                            to={`/projects/${projectId}/runs/${r.agent_run_id}`}
                            className="text-[10px] font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500"
                          >
                            Details
                          </Link>
                          <button
                            type="button"
                            className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 hover:text-orange-600"
                            onClick={async () => {
                              await api.cancelProjectRun(projectId, r.agent_run_id);
                              const next = await api.projectRuns(projectId, 120);
                              setRuns(next);
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="text-[10px] font-bold uppercase tracking-widest text-neutral-600 hover:text-orange-600"
                            onClick={async () => {
                              await api.retryProjectRun(projectId, r.agent_run_id);
                              const next = await api.projectRuns(projectId, 120);
                              setRuns(next);
                            }}
                          >
                            Retry
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === "tasks" && (
            <div className="glass overflow-hidden border-neutral-200">
              <table className="w-full text-sm">
                <thead className="bg-neutral-100 text-left text-[10px] font-bold text-neutral-600 uppercase tracking-widest">
                  <tr>
                    <th className="p-3">Priority</th>
                    <th className="p-3">Name</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={String(t.task_id)} className="border-t border-neutral-200">
                      <td className="p-3 text-neutral-600">{String(t.priority ?? "—")}</td>
                      <td className="p-3 text-neutral-800">{String(t.task_name ?? "")}</td>
                      <td className="p-3">
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-neutral-200 text-neutral-600 border border-neutral-300">
                          {String(t.status ?? "—")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="p-4 text-xs text-neutral-500 uppercase tracking-wide">Tasks are read-only here.</p>
            </div>
          )}

          {tab === "history" && (
            <div className="glass p-4 border-neutral-200">
              <h2 className="heading-sub mb-3">Change history</h2>
              <ul className="divide-y divide-neutral-200">
                {history.map((h, index) => (
                  <li key={String(h.change_history_id ?? h.event_log_id ?? index)} className="py-3 text-sm">
                    <p className="text-neutral-800">{String(h.title ?? h.change_type ?? "event")}</p>
                    <p className="text-xs text-neutral-600">
                      {String(h.source ?? "unknown")} · {String(h.created_at ?? "")}
                    </p>
                    {h.summary && <p className="text-xs text-neutral-600 mt-1">{String(h.summary)}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {tab === "settings" && (
            <div className="grid lg:grid-cols-2 gap-6">
              <div className="glass p-6 space-y-3 border-neutral-200">
                <h2 className="heading-sub">Project runtime settings</h2>
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">Repository URL</label>
                <input
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                  value={metadataForm.repository_url}
                  onChange={(e) => setMetadataForm((m) => ({ ...m, repository_url: e.target.value }))}
                />
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">Default branch</label>
                <input
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
                  value={metadataForm.default_branch}
                  onChange={(e) => setMetadataForm((m) => ({ ...m, default_branch: e.target.value }))}
                />
                <label className="block text-xs text-neutral-600 uppercase tracking-wide">
                  Runtime preferences JSON
                </label>
                <textarea
                  className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-xs min-h-[160px] text-neutral-900 font-mono"
                  value={metadataForm.runtime_preferences_json}
                  onChange={(e) =>
                    setMetadataForm((m) => ({ ...m, runtime_preferences_json: e.target.value }))
                  }
                />
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white"
                  onClick={async () => {
                    try {
                      const runtimePreferences = JSON.parse(metadataForm.runtime_preferences_json || "{}");
                      await api.updateProjectMetadata(projectId, {
                        repository_url: metadataForm.repository_url || undefined,
                        default_branch: metadataForm.default_branch || undefined,
                        runtime_preferences: runtimePreferences,
                      });
                    } catch (ex: unknown) {
                      setErr(ex instanceof Error ? ex.message : String(ex));
                    }
                  }}
                >
                  Save metadata
                </button>
              </div>

              <div className="glass p-6 space-y-3 border-neutral-200">
                <h2 className="heading-sub">Runtime check</h2>
                <pre className="text-xs text-neutral-700 whitespace-pre-wrap break-words bg-paper-field rounded-lg border border-neutral-300 p-3 max-h-[420px] overflow-y-auto">
                  {JSON.stringify(runtimeInfo ?? {}, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
