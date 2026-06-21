import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type AgentRun, type Project, type ProjectSummary } from "../api";

export default function Projects() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [summaries, setSummaries] = useState<Record<number, ProjectSummary>>({});
  const [runs, setRuns] = useState<Record<number, AgentRun[]>>({});
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    const batch = await api.batchProjectSummaries(50);
    const summaryRows = batch.summaries ?? [];
    const projectRows = summaryRows.map((row) => row.project);
    setProjects(projectRows);
    setSummaries(
      Object.fromEntries(summaryRows.map((row) => [row.project.project_id, row])) as Record<number, ProjectSummary>,
    );
    setRuns(
      Object.fromEntries(
        summaryRows.map((row) => [
          row.project.project_id,
          row.latest_run ? [row.latest_run as unknown as AgentRun] : [],
        ]),
      ),
    );
  };

  useEffect(() => {
    load().catch((e) => setErr(String(e.message)));
  }, []);

  return (
    <div className="space-y-8">
      <section className="glass p-6 border-orange-300/80 ring-2 ring-orange-100">
        <p className="heading-sub mb-2">Projects</p>
        <h1 className="heading-main text-2xl">Start or resume a build flow</h1>
        <p className="text-sm text-neutral-600 mt-3 max-w-2xl">
          Choose a project to continue from its current state. Create a new one only needs a name and optional purpose.
        </p>

        <form
          className="mt-5 grid lg:grid-cols-[1fr_2fr_auto] gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!name.trim()) return;
            setCreating(true);
            setErr(null);
            try {
              const created = await api.createProject({
                project_name: name.trim(),
                description: purpose.trim() || undefined,
                project_type: "Agentic build",
                status: "ACTIVE",
              });
              setName("");
              setPurpose("");
              navigate(`/projects/${created.project_id}/context`);
            } catch (ex: unknown) {
              setErr(ex instanceof Error ? ex.message : String(ex));
            } finally {
              setCreating(false);
            }
          }}
        >
          <input
            className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-3 text-sm text-neutral-900"
            placeholder="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="bg-paper-bright border border-neutral-300 rounded-lg px-3 py-3 text-sm text-neutral-900"
            placeholder="Purpose or goal, optional"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
          />
          <button
            type="submit"
            disabled={creating}
            className="px-5 py-3 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500 disabled:opacity-50"
          >
            {creating ? "Creating" : "Create project"}
          </button>
        </form>
      </section>

      <section className="space-y-3">
        {projects.map((project) => {
          const summary = summaries[project.project_id];
          const projectRuns = runs[project.project_id] ?? [];
          const docCount = summary?.counts.documents ?? 0;
          const taskCount = summary?.counts.tasks ?? 0;
          const runCount = summary?.counts.runs ?? 0;
          const latestRun = projectRuns[0] ?? summary?.latest_run;
          const next =
            docCount === 0
              ? "Add documents"
              : taskCount === 0
                ? "Serialize context"
                : runCount === 0
                  ? "Execute build"
                  : "Review and continue";

          return (
            <div key={project.project_id} className="glass p-5 border-neutral-200">
              <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                <div>
                  <p className="heading-sub mb-1">{next}</p>
                  <h2 className="heading-main text-lg">{project.project_name}</h2>
                  <p className="text-sm text-neutral-600 mt-2 max-w-2xl">{project.description || "No purpose written yet."}</p>
                  <div className="flex flex-wrap gap-2 mt-4 text-[10px] font-bold uppercase tracking-widest text-neutral-600">
                    <span className="rounded-full border border-neutral-300 bg-paper-field px-3 py-1">{docCount} docs</span>
                    <span className="rounded-full border border-neutral-300 bg-paper-field px-3 py-1">{taskCount} tasks</span>
                    <span className="rounded-full border border-neutral-300 bg-paper-field px-3 py-1">{runCount} runs</span>
                    {latestRun && (
                      <span className="rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-orange-700">
                        latest {latestRun.status}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link
                    to={`/projects/${project.project_id}/execute`}
                    className="px-4 py-2 rounded-lg bg-orange-600 text-white text-xs font-bold uppercase tracking-widest hover:bg-orange-500"
                  >
                    Open flow
                  </Link>
                  {latestRun && (
                    <Link
                      to={`/projects/${project.project_id}/runs/${latestRun.agent_run_id}`}
                      className="px-4 py-2 rounded-lg border border-neutral-400 text-neutral-700 text-xs font-bold uppercase tracking-widest hover:border-orange-300"
                    >
                      Latest run
                    </Link>
                  )}
                </div>
              </div>

              {projectRuns.length > 0 && (
                <div className="mt-4 border-t border-neutral-200 pt-3">
                  <p className="heading-sub mb-2">Previous runs</p>
                  <div className="grid md:grid-cols-3 gap-2">
                    {projectRuns.map((run) => (
                      <Link
                        key={run.agent_run_id}
                        to={`/projects/${project.project_id}/runs/${run.agent_run_id}`}
                        className="rounded-lg border border-neutral-300 bg-paper-field p-3 hover:border-orange-300"
                      >
                        <p className="font-bold text-neutral-900 text-sm">Run #{run.agent_run_id}</p>
                        <p className="text-xs text-neutral-600 mt-1">
                          {run.status ?? "UNKNOWN"} / {run.runtime_provider ?? "runtime"}
                        </p>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {projects.length === 0 && <p className="text-sm text-neutral-600">No projects yet. Create one above.</p>}
      </section>

      {err && <div className="text-sm text-neutral-700">{err}</div>}
    </div>
  );
}
