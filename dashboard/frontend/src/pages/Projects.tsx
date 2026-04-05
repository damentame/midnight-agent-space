import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Project } from "../api";

export default function Projects() {
  const [list, setList] = useState<Project[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const load = () =>
    api
      .projects()
      .then(setList)
      .catch((e) => setErr(String(e.message)));

  useEffect(() => {
    load();
  }, []);

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
                project_type: "General",
                status: "ACTIVE",
              });
              setName("");
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
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-sm font-bold uppercase tracking-widest text-white disabled:opacity-50"
          >
            {creating ? "…" : "Create"}
          </button>
        </form>
      </div>

      {err && (
        <div className="text-neutral-700 text-sm border border-neutral-300/80 rounded-lg p-3 bg-paper-lift/80">{err}</div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {list.map((p) => (
          <Link
            key={p.project_id}
            to={`/projects/${p.project_id}`}
            className="glass p-5 block hover:border-orange-300/60 transition-colors border-neutral-200 group"
          >
            <div className="flex justify-between items-start gap-2">
              <h2 className="heading-main text-sm group-hover:text-orange-600 transition-colors">
                {p.project_name ?? `Project ${p.project_id}`}
              </h2>
              {p.status && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-600 border border-neutral-300">
                  {p.status}
                </span>
              )}
            </div>
            <p className="text-neutral-600 text-sm mt-2 line-clamp-2">{p.description || "—"}</p>
            <p className="text-neutral-500 text-xs mt-3 uppercase tracking-wide">{p.project_type || "—"}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
