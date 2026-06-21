import { useMemo, useState } from "react";
import { api, type LocalPathBrowse } from "../api";
import { slugifyProjectName } from "../lib/projectWorkspace";

type Props = {
  repoPath: string;
  workspaceParentPath: string;
  onRepoPathChange: (value: string) => void;
  onWorkspaceParentChange: (value: string) => void;
  projectName: string;
};

export default function RepoPathSelector({
  repoPath,
  workspaceParentPath,
  onRepoPathChange,
  onWorkspaceParentChange,
  projectName,
}: Props) {
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [browse, setBrowse] = useState<LocalPathBrowse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const folderSlug = useMemo(() => slugifyProjectName(projectName), [projectName]);
  const plannedRepoPath = workspaceParentPath
    ? `${workspaceParentPath.replace(/[/\\]+$/, "")}\\${folderSlug}`
    : "";

  const displayValue = repoPath || workspaceParentPath;
  const selectionMode = repoPath ? "existing_repo" : workspaceParentPath ? "create_on_serialize" : "none";

  const loadPath = async (nextPath?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.browseLocalPaths(nextPath);
      setBrowse(result);
      setPath(result.current_path);
    } catch (ex: unknown) {
      setError(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  };

  const openPicker = () => {
    setOpen(true);
    const start = workspaceParentPath || repoPath || undefined;
    api
      .defaultWorkspaceParent()
      .then((result) => loadPath(start ?? result.parent_path))
      .catch(() => loadPath(start));
  };

  const selectCreateHere = () => {
    if (!browse?.current_path) return;
    onWorkspaceParentChange(browse.current_path);
    onRepoPathChange("");
    setOpen(false);
  };

  const selectExistingRepo = () => {
    if (!browse?.current_path) return;
    onRepoPathChange(browse.current_path);
    onWorkspaceParentChange("");
    setOpen(false);
  };

  return (
    <div className="lg:col-span-1">
      <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-1">
        Workspace (optional)
      </p>
      <div className="flex gap-2">
        <input
          className="min-w-0 flex-1 bg-paper-bright border border-neutral-300 rounded-lg px-3 py-2 text-sm text-neutral-900"
          placeholder="Parent folder or existing repo path"
          value={displayValue}
          onChange={(e) => {
            const next = e.target.value;
            if (selectionMode === "existing_repo") {
              onRepoPathChange(next);
            } else {
              onWorkspaceParentChange(next);
              onRepoPathChange("");
            }
          }}
        />
        <button
          type="button"
          onClick={openPicker}
          className="shrink-0 px-4 py-2 rounded-lg border border-neutral-400 text-neutral-700 text-xs font-bold uppercase tracking-widest hover:border-orange-400 hover:text-orange-700"
        >
          Browse
        </button>
      </div>
      {selectionMode === "create_on_serialize" && (
        <p className="mt-1 text-[11px] text-orange-800">
          On serialize: create <span className="font-bold">{folderSlug}</span>, run{" "}
          <span className="font-mono">git init</span>, and index the codebase at{" "}
          <span className="break-all font-mono">{plannedRepoPath}</span>
        </p>
      )}
      {selectionMode === "existing_repo" && (
        <p className="mt-1 text-[11px] text-neutral-500 break-all">Existing repository: {repoPath}</p>
      )}

      {open && (
        <div className="fixed inset-0 z-50 bg-neutral-950/35 p-4 flex items-center justify-center">
          <div className="w-full max-w-3xl max-h-[82vh] overflow-hidden rounded-lg border border-neutral-300 bg-paper-bright shadow-2xl">
            <div className="border-b border-neutral-300 p-4 flex items-start justify-between gap-4">
              <div>
                <p className="heading-sub">Workspace location</p>
                <p className="text-xs text-neutral-600 mt-1 break-all">
                  {browse?.current_path ?? "Loading local folders..."}
                </p>
                {browse && (
                  <span
                    className={`inline-flex mt-2 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
                      browse.is_git_repo
                        ? "border-orange-300 bg-orange-50 text-orange-700"
                        : "border-neutral-300 bg-paper-field text-neutral-600"
                    }`}
                  >
                    {browse.is_git_repo ? "Existing git repository" : "Parent folder"}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-neutral-300 px-3 py-1 text-xs font-bold uppercase tracking-widest text-neutral-600 hover:border-orange-300"
              >
                Close
              </button>
            </div>

            <div className="p-4 border-b border-neutral-300 space-y-3">
              <p className="text-xs text-neutral-600 leading-relaxed">
                Choose a <span className="font-bold">parent folder</span> for a new project (folder + git are created when
                you serialize). Or open an <span className="font-bold">existing repository</span> to index that codebase on
                serialize.
              </p>
              <div className="flex flex-wrap gap-2">
                {browse?.parent_path && (
                  <button
                    type="button"
                    onClick={() => loadPath(browse.parent_path ?? undefined)}
                    className="rounded-md border border-neutral-300 bg-paper-field px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-neutral-700 hover:border-orange-300"
                  >
                    Up one folder
                  </button>
                )}
                {browse?.home_path && (
                  <button
                    type="button"
                    onClick={() => loadPath(browse.home_path)}
                    className="rounded-md border border-neutral-300 bg-paper-field px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-neutral-700 hover:border-orange-300"
                  >
                    Home
                  </button>
                )}
                {browse?.drives.map((drive) => (
                  <button
                    key={drive}
                    type="button"
                    onClick={() => loadPath(drive)}
                    className="rounded-md border border-neutral-300 bg-paper-field px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-neutral-700 hover:border-orange-300"
                  >
                    {drive}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-neutral-300 bg-paper-field px-3 py-2 text-xs text-neutral-800"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => loadPath(path)}
                  className="rounded-lg border border-neutral-400 px-3 py-2 text-xs font-bold uppercase tracking-widest text-neutral-700 hover:border-orange-400"
                >
                  Go
                </button>
              </div>
              {error && <p className="text-xs text-neutral-800">{error}</p>}
            </div>

            <div className="max-h-[42vh] overflow-y-auto p-2">
              {loading && <p className="p-3 text-sm text-neutral-600">Loading folders...</p>}
              {!loading && browse && !browse.is_git_repo && browse.git_repos.length > 0 && (
                <div className="mb-2 rounded-lg border border-orange-200 bg-orange-50 p-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-orange-700">
                    Git repositories nearby
                  </p>
                  <div className="mt-2 space-y-1">
                    {browse.git_repos.map((repo) => (
                      <button
                        key={repo.path}
                        type="button"
                        onClick={() => loadPath(repo.path)}
                        className="w-full rounded-md border border-orange-200 bg-paper-bright px-3 py-2 text-left hover:border-orange-400"
                      >
                        <span className="block text-sm font-bold text-neutral-900">{repo.name}</span>
                        <span className="block text-xs text-neutral-600 break-all">{repo.path}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {!loading &&
                browse?.folders.map((folder) => (
                  <button
                    key={folder.path}
                    type="button"
                    onClick={() => loadPath(folder.path)}
                    className="w-full rounded-md px-3 py-2 text-left hover:bg-orange-50 flex items-center justify-between gap-3"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-bold text-neutral-900">{folder.name}</span>
                      <span className="block truncate text-xs text-neutral-500">{folder.path}</span>
                    </span>
                    {folder.is_git_repo && (
                      <span className="shrink-0 rounded-full border border-orange-300 bg-orange-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-orange-700">
                        Git
                      </span>
                    )}
                  </button>
                ))}
              {!loading && browse?.folders.length === 0 && (
                <p className="p-3 text-sm text-neutral-600">No folders found here.</p>
              )}
            </div>

            <div className="border-t border-neutral-300 p-4 space-y-3">
              <p className="text-xs text-neutral-600 break-all">Selected: {browse?.current_path ?? path}</p>
              <div className="flex flex-col sm:flex-row flex-wrap gap-2 justify-end">
                {browse && !browse.is_git_repo && (
                  <button
                    type="button"
                    disabled={!browse}
                    onClick={selectCreateHere}
                    className="rounded-lg bg-orange-600 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white hover:bg-orange-500 disabled:opacity-50"
                  >
                    {`Create "${folderSlug}" here`}
                  </button>
                )}
                {browse?.is_git_repo && (
                  <button
                    type="button"
                    disabled={!browse}
                    onClick={selectExistingRepo}
                    className="rounded-lg bg-orange-600 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white hover:bg-orange-500 disabled:opacity-50"
                  >
                    Use this repository
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
