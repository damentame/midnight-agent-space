import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type TemporalExecutionRow } from "../api";

type DbRun = Record<string, unknown>;

export default function Workflows() {
  const [dbRuns, setDbRuns] = useState<DbRun[]>([]);
  const [temporal, setTemporal] = useState<TemporalExecutionRow[]>([]);
  const [targets, setTargets] = useState<Record<number, string | null>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setErr(null);
    api
      .workflowRuns()
      .then((r) => setDbRuns(r as DbRun[]))
      .catch((e) => setErr(e.message));
    api
      .temporalExecutions(40)
      .then(setTemporal)
      .catch(() => setTemporal([]));
  }, []);

  useEffect(() => {
    const ids = dbRuns
      .map((r) => Number(r.workflow_run_id))
      .filter((n) => Number.isFinite(n));
    ids.forEach((id) => {
      api
        .temporalTargetFromWorkflowRun(id)
        .then((t) => {
          setTargets((prev) => ({ ...prev, [id]: t.derived_workflow_id }));
        })
        .catch(() => {});
    });
  }, [dbRuns]);

  return (
    <div className="space-y-10">
      <div>
        <p className="heading-sub mb-1">Monitoring</p>
        <h1 className="heading-main text-2xl">Workflows</h1>
        <p className="text-neutral-600 text-sm mt-2">
          Database rows in <code className="text-neutral-700">main.workflow_run</code> plus live Temporal executions.
        </p>
      </div>

      {err && <p className="text-neutral-600 text-sm">{err}</p>}

      <section>
        <h2 className="heading-sub mb-3">Temporal (live cluster)</h2>
        <div className="glass overflow-x-auto border-neutral-200">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="text-left text-[10px] font-bold uppercase tracking-widest text-neutral-600 border-b border-neutral-200">
              <tr>
                <th className="p-3">Workflow id</th>
                <th className="p-3">Type</th>
                <th className="p-3">Status</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {temporal.map((r) => (
                <tr key={`${r.workflow_id}-${r.run_id}`} className="border-b border-neutral-200 hover:bg-paper-lift/60">
                  <td className="p-3 font-mono text-xs text-neutral-800 max-w-[200px] truncate">{r.workflow_id}</td>
                  <td className="p-3 text-neutral-600">{r.workflow_type}</td>
                  <td className="p-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-600">{r.status}</span>
                  </td>
                  <td className="p-3 text-right">
                    <Link
                      to={`/workflows/live/${encodeURIComponent(r.workflow_id)}`}
                      className="text-[10px] font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500"
                    >
                      Live →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="heading-sub mb-3">Database workflow_run</h2>
        <div className="glass overflow-x-auto border-neutral-200">
          <table className="w-full text-sm min-w-[560px]">
            <thead className="text-left text-[10px] font-bold uppercase tracking-widest text-neutral-600 border-b border-neutral-200">
              <tr>
                <th className="p-3">ID</th>
                <th className="p-3">Name</th>
                <th className="p-3">Project</th>
                <th className="p-3">Status</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {dbRuns.map((r) => {
                const id = Number(r.workflow_run_id);
                const derived = targets[id];
                return (
                  <tr key={id} className="border-b border-neutral-200">
                    <td className="p-3 font-mono text-xs text-neutral-600">{id}</td>
                    <td className="p-3 text-neutral-800">{String(r.workflow_name ?? "—")}</td>
                    <td className="p-3 text-neutral-600">{String(r.project_id ?? "—")}</td>
                    <td className="p-3 text-[10px] uppercase tracking-wider text-neutral-600">{String(r.status ?? "—")}</td>
                    <td className="p-3 text-right">
                      {derived ? (
                        <Link
                          to={`/workflows/live/${encodeURIComponent(derived)}`}
                          className="text-[10px] font-bold uppercase tracking-widest text-orange-600 hover:text-orange-500"
                        >
                          Live →
                        </Link>
                      ) : (
                        <span className="text-[10px] text-neutral-500">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-neutral-500 mt-2">
          Child workflows (e.g. <code className="text-neutral-600">task-exec-…</code>) need a manual id — use the Temporal table above or paste on the Live page.
        </p>
      </section>
    </div>
  );
}
