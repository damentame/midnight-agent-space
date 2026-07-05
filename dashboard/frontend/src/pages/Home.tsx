import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AgentRun, type Project, type ProjectSummary } from "../api";
import { formatCostUsd, formatTokenCount, extractTokenUsage } from "../lib/tokenUsage";

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [summaries, setSummaries] = useState<Record<number, ProjectSummary>>({});
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.batchProjectSummaries(8), api.agentRuns(undefined, 10)])
      .then(([batch, runRows]) => {
        const summaryRows = batch.summaries ?? [];
        setProjects(summaryRows.map((row) => row.project));
        setRuns(runRows);
        setSummaries(
          Object.fromEntries(summaryRows.map((row) => [row.project.project_id, row])) as Record<number, ProjectSummary>,
        );
      })
      .catch((e) => setErr(String(e.message)));
  }, []);

  const activeProject = projects.find((project) => {
    const summary = summaries[project.project_id];
    return (summary?.counts.documents ?? 0) > 0 || (summary?.counts.runs ?? 0) === 0;
  });
  const recentRun = runs[0];

  return (
    <div className="space-y-8">
      <section className="glass p-6 sm:p-8 border-orange-300/80 ring-2 ring-orange-100">
        <p className="heading-sub mb-3">Agentic project flow</p>
        <h1 className="heading-main text-2xl sm:text-4xl max-w-3xl">
          Create context. Serialize the goal. Execute agents. Review the build.
        </h1>
        <p className="text-neutral-600 text-sm sm:text-base mt-4 max-w-2xl">
          Midnight is now focused on one path: create a project, add documents, turn them into agent-ready context,
          run the build with live visibility, then review and use the result.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/projects"
            className="px-5 py-3 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500"
          >
            Start or continue project
          </Link>
          {activeProject && (
            <Link
              to={`/projects/${activeProject.project_id}/execute`}
              className="px-5 py-3 rounded-lg bg-neutral-900 text-white text-xs font-bold uppercase tracking-widest hover:bg-neutral-700"
            >
              Continue active flow
            </Link>
          )}
        </div>
      </section>

      <section className="grid lg:grid-cols-3 gap-4">
        {[
          ["1", "Create project", "Name the project and define the local repo only when execution is needed."],
          ["2", "Serialize purpose", "Upload docs, images, and design assets, then generate the task board."],
          ["3", "Execute and review", "Run agents, watch live progress, inspect outputs, and launch preview."],
        ].map(([step, title, copy]) => (
          <div key={step} className="glass p-5 border-neutral-200">
            <p className="heading-sub text-orange-600">Step {step}</p>
            <h2 className="text-sm font-bold text-neutral-900 mt-2">{title}</h2>
            <p className="text-sm text-neutral-600 mt-2">{copy}</p>
          </div>
        ))}
      </section>

      <section className="grid lg:grid-cols-2 gap-6">
        <div className="glass p-5 border-neutral-200">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="heading-sub">Projects in flow</h2>
            <Link to="/projects" className="text-[10px] font-bold uppercase tracking-widest text-orange-600">
              View all
            </Link>
          </div>
          <div className="space-y-3">
            {projects.slice(0, 5).map((project) => {
              const summary = summaries[project.project_id];
              const documentCount = summary?.counts.documents ?? 0;
              const runCount = summary?.counts.runs ?? 0;
              const nextLabel = documentCount === 0 ? "Add context" : runCount === 0 ? "Serialize and run" : "Review flow";
              return (
                <Link
                  key={project.project_id}
                  to={`/projects/${project.project_id}/context`}
                  className="block rounded-lg border border-neutral-300 bg-paper-field p-3 hover:border-orange-300"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold text-neutral-900">{project.project_name}</p>
                      <p className="text-xs text-neutral-600 mt-1">
                        {documentCount} documents / {summary?.counts.tasks ?? 0} tasks / {runCount} runs
                        {summary?.latest_run?.token_usage?.totals?.total_tokens
                          ? ` · ${formatTokenCount(summary.latest_run.token_usage.totals.total_tokens)} tokens (${formatCostUsd(summary.latest_run.token_usage.totals.cost_usd)})`
                          : ""}
                      </p>
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-orange-600">{nextLabel}</span>
                  </div>
                </Link>
              );
            })}
            {projects.length === 0 && <p className="text-sm text-neutral-600">No projects yet. Start by creating one.</p>}
          </div>
        </div>

        <div className="glass p-5 border-neutral-200">
          <h2 className="heading-sub mb-4">Recent execution visibility</h2>
          <div className="space-y-3">
            {runs.slice(0, 6).map((run) => {
              const runUsage = extractTokenUsage(run.result_payload);
              return (
              <Link
                key={run.agent_run_id}
                to={run.project_id ? `/projects/${run.project_id}/runs/${run.agent_run_id}` : "/projects"}
                className="block rounded-lg border border-neutral-300 bg-paper-field p-3 hover:border-orange-300"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-bold text-neutral-900">Run #{run.agent_run_id}</p>
                    <p className="text-xs text-neutral-600 mt-1">
                      project {run.project_id ?? "-"} / {run.runtime_provider ?? "runtime"} / {run.created_at ?? ""}
                      {runUsage?.totals?.total_tokens
                        ? ` · ${formatTokenCount(runUsage.totals.total_tokens)} tokens`
                        : ""}
                    </p>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-600">
                    {run.status ?? "UNKNOWN"}
                  </span>
                </div>
              </Link>
            );
            })}
            {!recentRun && <p className="text-sm text-neutral-600">No runs yet. Execute a project to create a monitorable run.</p>}
          </div>
        </div>
      </section>

      {err && <div className="text-sm text-neutral-700">{err}</div>}
    </div>
  );
}
