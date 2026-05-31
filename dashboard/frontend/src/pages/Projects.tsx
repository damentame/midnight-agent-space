import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "../api";

export default function Projects() {
  const [list, setList] = useState<Project[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [projectType, setProjectType] = useState("General");
  const [description, setDescription] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<Record<number, Partial<Project>>>({});

  const load = () =>
    api
      .projects({ q: query || undefined, status: status || undefined, limit: 300 })
      .then(setList)
      .catch((e) => setErr(String(e.message)));

  useEffect(() => {
    load();
  }, [query, status]);

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <p className="heading-sub mb-1">Directory</p>
          <h1 className="heading-main text-2xl">Projects</h1>
          <p className="text-neutral-600 text-sm mt-2">Select a project or create one.</p>
        </div>
        <form
          className="flex flex-wrap gap-2 items-center"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!name.trim()) return;
            setCreating(true);
            setErr(null);
            try {
              await api.createProject({
                project_name: name.trim(),
                project_type: projectType || "General",
                description: description.trim() || undefined,
                status: "ACTIVE",
              });
              setName("");
              setProjectType("General");
              setDescription("");
              await load();
            } catch (ex: unknown) {
              setErr(ex instanceof Error ? ex.message : String(ex));
            } finally {
              setCreating(false);
            }
          }}
        >
          <input
            className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm w-48 focus:outline-none focus:ring-1 focus:ring-orange-500 text-neutral-900"
            placeholder="New project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm w-32 focus:outline-none focus:ring-1 focus:ring-orange-500 text-neutral-900"
            placeholder="Type"
            value={projectType}
            onChange={(e) => setProjectType(e.target.value)}
          />
          <input
            className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm w-56 focus:outline-none focus:ring-1 focus:ring-orange-500 text-neutral-900"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white disabled:opacity-50"
          >
            {creating ? "…" : "Create"}
          </button>
        </form>
      </div>

      <div className="glass p-4 border-neutral-200 flex flex-wrap gap-3 items-end">
        <label className="block">
          <span className="heading-sub">Search</span>
          <input
            className="mt-1 bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm w-64 text-neutral-900"
            placeholder="name, description, type"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="heading-sub">Status</span>
          <select
            className="mt-1 bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm w-40 text-neutral-900"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="ARCHIVED">ARCHIVED</option>
          </select>
        </label>
      </div>

      {err && (
        <div className="text-neutral-700 text-sm border border-neutral-300/80 rounded-lg p-3 bg-paper-lift/80">{err}</div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {list.map((p) => (
          <div
            key={p.project_id}
            className="glass p-5 block hover:border-orange-300/60 transition-colors border-neutral-200 group"
          >
            <div className="flex justify-between items-start gap-3">
              <Link to={`/projects/${p.project_id}`} className="block">
                <h2 className="heading-main text-sm group-hover:text-orange-600 transition-colors">
                  {p.project_name ?? `Project ${p.project_id}`}
                </h2>
              </Link>
              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-600 border border-neutral-300">
                {p.status ?? "UNKNOWN"}
              </span>
            </div>
            <p className="text-neutral-600 text-sm mt-2 line-clamp-2">{p.description || "—"}</p>
            <p className="text-neutral-500 text-xs mt-3 uppercase tracking-wide">{p.project_type || "—"}</p>

            <div className="mt-4 pt-3 border-t border-neutral-200 space-y-2">
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  className="bg-paper-bright border border-neutral-300 rounded-lg px-2 py-1.5 text-xs text-neutral-900"
                  placeholder="Edit name"
                  value={String(editing[p.project_id]?.project_name ?? p.project_name ?? "")}
                  onChange={(e) =>
                    setEditing((prev) => ({
                      ...prev,
                      [p.project_id]: {
                        ...prev[p.project_id],
                        project_name: e.target.value,
                      },
                    }))
                  }
                />
                <input
                  className="bg-paper-bright border border-neutral-300 rounded-lg px-2 py-1.5 text-xs text-neutral-900"
                  placeholder="Edit type"
                  value={String(editing[p.project_id]?.project_type ?? p.project_type ?? "")}
                  onChange={(e) =>
                    setEditing((prev) => ({
                      ...prev,
                      [p.project_id]: {
                        ...prev[p.project_id],
                        project_type: e.target.value,
                      },
                    }))
                  }
                />
              </div>
              <textarea
                className="w-full bg-paper-bright border border-neutral-300 rounded-lg px-2 py-1.5 text-xs min-h-[70px] text-neutral-900"
                placeholder="Edit description"
                value={String(editing[p.project_id]?.description ?? p.description ?? "")}
                onChange={(e) =>
                  setEditing((prev) => ({
                    ...prev,
                    [p.project_id]: {
                      ...prev[p.project_id],
                      description: e.target.value,
                    },
                  }))
                }
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={savingId === p.project_id}
                  className="px-3 py-1 rounded border border-orange-600 text-orange-600 text-[10px] font-bold uppercase tracking-widest hover:bg-orange-50 disabled:opacity-50"
                  onClick={async () => {
                    setErr(null);
                    setSavingId(p.project_id);
                    try {
                      const draft = editing[p.project_id] ?? {};
                      await api.patchProject(p.project_id, draft);
                      await load();
                    } catch (ex: unknown) {
                      setErr(ex instanceof Error ? ex.message : String(ex));
                    } finally {
                      setSavingId(null);
                    }
                  }}
                >
                  Save edits
                </button>
                {String(p.status ?? "").toUpperCase() !== "ARCHIVED" && (
                  <button
                    type="button"
                    disabled={savingId === p.project_id}
                    className="px-3 py-1 rounded border border-neutral-400 text-neutral-600 text-[10px] font-bold uppercase tracking-widest hover:bg-neutral-100 disabled:opacity-50"
                    onClick={async () => {
                      setErr(null);
                      setSavingId(p.project_id);
                      try {
                        await api.archiveProject(p.project_id);
                        await load();
                      } catch (ex: unknown) {
                        setErr(ex instanceof Error ? ex.message : String(ex));
                      } finally {
                        setSavingId(null);
                      }
                    }}
                  >
                    Archive
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
