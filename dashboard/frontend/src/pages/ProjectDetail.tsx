import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Project } from "../api";

type Tab = "details" | "documents" | "tasks";

export default function ProjectDetail() {
  const { id } = useParams();
  const projectId = Number(id);
  const [tab, setTab] = useState<Tab>("details");
  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<Record<string, unknown>[]>([]);
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ project_name: "", description: "", status: "", project_type: "" });

  const [wf, setWf] = useState({
    agent_id: 2,
    agent_provider: "cursor",
    execute_mode: "fast" as "fast" | "complex",
    concurrent_tasks: false,
    batch_tasks: false,
  });
  const [wfMsg, setWfMsg] = useState<string | null>(null);

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
  }, [projectId]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || tab !== "documents") return;
    api.documents(projectId).then(setDocs).catch((e) => setErr(e.message));
  }, [projectId, tab]);

  useEffect(() => {
    if (!Number.isFinite(projectId) || tab !== "tasks") return;
    api.tasks(projectId).then(setTasks).catch((e) => setErr(e.message));
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
              {(["details", "documents", "tasks"] as Tab[]).map((t) => (
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

          {tab === "details" && (
            <div className="space-y-6">
              <form
                className="glass p-6 space-y-4 max-w-xl"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setSaving(true);
                  setErr(null);
                  try {
                    const updated = await api.updateProject(projectId, {
                      project_name: form.project_name || undefined,
                      description: form.description || undefined,
                      status: form.status || undefined,
                      project_type: form.project_type || undefined,
                    });
                    setProject(updated);
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
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </form>

              <div className="glass p-6 space-y-4 border-neutral-200">
                <h2 className="heading-sub">Run document serialization</h2>
                <p className="text-xs text-neutral-600">
                  Same as <code className="text-neutral-700">temporal/main.py</code> — worker + API keys required.
                </p>
                <div className="grid sm:grid-cols-2 gap-3 text-sm">
                  <label className="block">
                    <span className="text-neutral-600 text-xs uppercase tracking-wide">Agent ID</span>
                    <input
                      type="number"
                      className="mt-1 w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-neutral-900"
                      value={wf.agent_id}
                      onChange={(e) => setWf((w) => ({ ...w, agent_id: Number(e.target.value) }))}
                    />
                  </label>
                  <label className="block">
                    <span className="text-neutral-600 text-xs uppercase tracking-wide">Provider</span>
                    <select
                      className="mt-1 w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-neutral-900"
                      value={wf.agent_provider}
                      onChange={(e) => setWf((w) => ({ ...w, agent_provider: e.target.value }))}
                    >
                      <option value="cursor">cursor</option>
                      <option value="codex">codex</option>
                      <option value="claude-code">claude-code</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-neutral-600 text-xs uppercase tracking-wide">Execute mode</span>
                    <select
                      className="mt-1 w-full bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-neutral-900"
                      value={wf.execute_mode}
                      onChange={(e) =>
                        setWf((w) => ({ ...w, execute_mode: e.target.value as "fast" | "complex" }))
                      }
                    >
                      <option value="fast">fast</option>
                      <option value="complex">complex</option>
                    </select>
                  </label>
                  <div className="flex flex-col gap-2 justify-end">
                    <label className="flex items-center gap-2 text-neutral-600 text-xs uppercase tracking-wide">
                      <input
                        type="checkbox"
                        checked={wf.concurrent_tasks}
                        onChange={(e) =>
                          setWf((w) => ({ ...w, concurrent_tasks: e.target.checked, batch_tasks: false }))
                        }
                      />
                      Concurrent tasks
                    </label>
                    <label className="flex items-center gap-2 text-neutral-600 text-xs uppercase tracking-wide">
                      <input
                        type="checkbox"
                        checked={wf.batch_tasks}
                        onChange={(e) =>
                          setWf((w) => ({ ...w, batch_tasks: e.target.checked, concurrent_tasks: false }))
                        }
                      />
                      Batch tasks
                    </label>
                  </div>
                </div>
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg border border-orange-600 text-orange-600 text-xs font-bold uppercase tracking-widest hover:bg-orange-50"
                  onClick={async () => {
                    setWfMsg(null);
                    try {
                      const r = await api.startWorkflow({
                        agent_id: wf.agent_id,
                        project_id: projectId,
                        agent_provider: wf.agent_provider,
                        execute_mode: wf.execute_mode,
                        concurrent_tasks: wf.concurrent_tasks,
                        batch_tasks: wf.batch_tasks,
                      });
                      setWfMsg(`Started: ${r.workflow_id}`);
                    } catch (ex: unknown) {
                      setWfMsg(ex instanceof Error ? ex.message : String(ex));
                    }
                  }}
                >
                  Start workflow
                </button>
                {wfMsg && <p className="text-xs text-neutral-600 break-all">{wfMsg}</p>}

                <div className="pt-2 border-t border-neutral-200 space-y-2">
                  <p className="heading-sub">Temporal monitor</p>
                  <p className="text-xs text-neutral-500">
                    Expected workflow id:{" "}
                    <code className="text-neutral-700">
                      document-serialization-{projectId}-{wf.agent_id}
                    </code>
                  </p>
                  <Link
                    to={`/workflows/live/${encodeURIComponent(`document-serialization-${projectId}-${wf.agent_id}`)}`}
                    className="inline-block text-xs font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500"
                  >
                    Open live activity view →
                  </Link>
                </div>
              </div>
            </div>
          )}

          {tab === "documents" && (
            <div className="glass p-6 space-y-4 border-neutral-200">
              <h2 className="heading-sub">Documents</h2>
              <p className="text-xs text-neutral-600">
                Upload text or code files; stored in <code className="text-neutral-700">main.project_document</code>.
              </p>
              <label className="flex flex-col gap-2 border border-dashed border-neutral-300 rounded-xl p-8 text-center cursor-pointer hover:border-orange-400/50 bg-paper-field/50">
                <span className="text-neutral-600 text-sm">Drop file or click to upload</span>
                <input
                  type="file"
                  className="hidden"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    try {
                      await api.uploadDocument(projectId, f);
                      const d = await api.documents(projectId);
                      setDocs(d as Record<string, unknown>[]);
                    } catch (ex: unknown) {
                      setErr(ex instanceof Error ? ex.message : String(ex));
                    }
                    e.target.value = "";
                  }}
                />
              </label>
              <ul className="divide-y divide-neutral-200">
                {docs.map((d) => (
                  <li key={String(d.document_id)} className="py-3 flex justify-between gap-4 text-sm">
                    <div>
                      <p className="text-neutral-800">{String(d.document_name)}</p>
                      <p className="text-neutral-600 text-xs">
                        {String(d.serialization_status ?? "")} · {String(d.file_extension ?? "")}
                      </p>
                    </div>
                    {String(d.serialization_status ?? "PENDING") === "PENDING" && (
                      <button
                        type="button"
                        className="text-neutral-600 hover:text-orange-600 text-xs uppercase tracking-wide"
                        onClick={async () => {
                          await api.deleteDocument(projectId, Number(d.document_id));
                          setDocs((prev) => prev.filter((x) => x.document_id !== d.document_id));
                        }}
                      >
                        Remove
                      </button>
                    )}
                  </li>
                ))}
              </ul>
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
        </>
      )}
    </div>
  );
}
