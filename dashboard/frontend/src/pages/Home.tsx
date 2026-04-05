import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Stats } from "../api";

export default function Home() {
  const [s, setS] = useState<Stats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .stats()
      .then(setS)
      .catch((e) => setErr(String(e.message)));
  }, []);

  if (err) {
    return (
      <div className="glass p-6 border border-neutral-200 text-neutral-700 text-sm">
        Cannot reach API. Start backend:{" "}
        <code className="text-orange-600">python -m uvicorn dashboard.backend.main:app --port 8001</code>
        <br />
        <span className="text-neutral-500 mt-2 block">{err}</span>
      </div>
    );
  }

  if (!s) {
    return <p className="text-neutral-500 text-sm">Loading…</p>;
  }

  return (
    <div className="space-y-10">
      <div>
        <p className="heading-sub mb-2">Overview</p>
        <h1 className="heading-main text-2xl sm:text-3xl">Dashboard</h1>
        <p className="text-neutral-600 text-sm mt-2">
          Projects, tasks, and recent workflow activity from the same database as the worker.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          ["Projects", s.project_count],
          ["Tasks", s.task_count],
          ["Active workflows", s.active_workflow_count],
        ].map(([label, n]) => (
          <div key={label} className="glass p-5 border-neutral-200">
            <p className="heading-sub text-[10px] mb-2">{String(label)}</p>
            <span className="stat-number">{n}</span>
          </div>
        ))}
      </div>

      <div className="glass p-5 border-neutral-200">
        <h2 className="heading-sub mb-4">Recent workflow runs</h2>
        {s.recent_workflow_runs.length === 0 ? (
          <p className="text-neutral-600 text-sm">No runs yet.</p>
        ) : (
          <ul className="space-y-2">
            {s.recent_workflow_runs.map((r) => (
              <li
                key={r.workflow_run_id}
                className="flex justify-between gap-4 text-sm border-b border-neutral-200/90 pb-2 last:border-0"
              >
                <span className="text-neutral-800">{r.workflow_name ?? "—"}</span>
                <span className="text-neutral-600 text-xs">
                  project {r.project_id ?? "—"} ·{" "}
                  <span
                    className={
                      r.status === "COMPLETED"
                        ? "text-neutral-800"
                        : r.status === "FAILED"
                          ? "text-neutral-600"
                          : "text-orange-600"
                    }
                  >
                    {r.status}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-6 flex flex-wrap gap-4">
          <Link
            to="/projects"
            className="text-xs font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500"
          >
            Projects →
          </Link>
          <Link
            to="/workflows/live"
            className="text-xs font-bold uppercase tracking-widest text-neutral-600 hover:text-orange-600"
          >
            Live monitor →
          </Link>
        </div>
      </div>
    </div>
  );
}
